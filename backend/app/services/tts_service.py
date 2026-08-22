"""Speech synthesis for answer playback.

Answers are immutable once written, so audio is cached on a hash of the text
that produced it rather than on the message id — the same answer reached from
another conversation hits the same entry.

Unlike the web-search client, a failure here raises rather than returning
empty. There, a missing result still leaves an answer on the page; here,
silence *is* the failure, and the reader deserves to be told.
"""

import asyncio
import hashlib
import inspect
import logging

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.core.logging import Timer, log_event
from app.core.text import split_for_speech
from app.services.cache import cache_get_bytes, cache_set_bytes

logger = logging.getLogger(__name__)

#: Container type per response format, for the endpoint's Content-Type.
MEDIA_TYPES = {
    "mp3": "audio/mpeg",
    "opus": "audio/ogg",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "wav": "audio/wav",
    "pcm": "audio/L16",
}


class SpeechError(Exception):
    """Synthesis failed. Distinct from "nothing to say", which is not an error."""


_client: AsyncOpenAI | None = None


def get_speech_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=get_settings().openai_api_key)
    return _client


def speech_enabled() -> bool:
    settings = get_settings()
    return bool(settings.tts_enabled and settings.openai_api_key)


def cache_key(text: str, *, voice: str, model: str, fmt: str) -> str:
    digest = hashlib.sha256(f"{model}|{voice}|{fmt}|{text}".encode("utf-8")).hexdigest()
    return f"tts:{digest[:40]}"


async def _response_bytes(response) -> bytes:
    """Audio out of the SDK's binary response wrapper.

    requirements.txt pins only `openai>=1.40`, and that wrapper has carried
    `aread()`, `read()` and a plain `content` property across versions in that
    range. Probing costs nothing and keeps a minor SDK bump from breaking
    playback in a way that would only show up at runtime.
    """
    for attribute in ("aread", "read"):
        method = getattr(response, attribute, None)
        if method is None:
            continue
        result = method()
        return await result if inspect.isawaitable(result) else result
    return response.content


async def synthesize(
    text: str,
    *,
    voice: str | None = None,
    model: str | None = None,
    fmt: str | None = None,
) -> bytes:
    """Speech for one answer: cache, then chunk, then the API.

    Segments are concatenated bytewise. Players resync on MP3 frame headers so
    a joined file plays; expect a faint seam at the joins. Most answers are a
    single segment and never take that path.
    """
    settings = get_settings()
    voice = voice or settings.tts_voice
    model = model or settings.tts_model
    fmt = fmt or settings.tts_format

    text = text.strip()[: settings.tts_max_chars]
    if not text:
        raise SpeechError("nothing speakable in this answer")

    key = cache_key(text, voice=voice, model=model, fmt=fmt)
    cached = await cache_get_bytes(key)
    if cached:
        log_event(logger, "tts_cache_hit", characters=len(text))
        return cached

    segments = split_for_speech(text, settings.tts_chunk_chars)
    client = get_speech_client()
    # Only the gpt-4o speech models accept delivery instructions; tts-1 and
    # tts-1-hd reject the parameter outright.
    extra = (
        {"instructions": settings.tts_instructions}
        if settings.tts_instructions and model.startswith("gpt-4o")
        else {}
    )

    async def render(segment: str) -> bytes:
        """One segment, cached on its own text.

        Per-segment keys as well as the whole-answer key above: a reader who
        replays after the answer was extended, or two answers that share an
        opening, reuse work instead of paying for it twice.
        """
        segment_key = cache_key(segment, voice=voice, model=model, fmt=fmt)
        hit = await cache_get_bytes(segment_key)
        if hit:
            return hit
        async with limiter:
            response = await client.audio.speech.create(
                model=model,
                voice=voice,
                input=segment,
                response_format=fmt,
                **extra,
            )
        rendered = await _response_bytes(response)
        await cache_set_bytes(segment_key, rendered, ttl=settings.tts_cache_ttl_seconds)
        return rendered

    # Segments used to be synthesised in a for-loop, so a three-segment answer
    # cost three round trips end to end and the reader waited for all of them.
    # They are independent, so they go concurrently and the wait becomes the
    # slowest one rather than the sum. Bounded, because the answer cap allows
    # enough segments to matter and OpenAI rate-limits per key.
    limiter = asyncio.Semaphore(settings.tts_max_concurrency)
    audio = bytearray()
    try:
        with Timer() as timer:
            # gather preserves order, which is what keeps the sentences in the
            # sequence they were written
            for rendered in await asyncio.gather(*(render(s) for s in segments)):
                audio.extend(rendered)
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller as 502
        logger.warning("speech synthesis failed: %s", exc)
        raise SpeechError(str(exc)) from exc

    if not audio:
        raise SpeechError("speech API returned no audio")

    result = bytes(audio)
    await cache_set_bytes(key, result, ttl=settings.tts_cache_ttl_seconds)
    log_event(
        logger,
        "tts_synthesized",
        characters=len(text),
        segments=len(segments),
        bytes=len(result),
        latency_ms=timer.ms,
    )
    return result
