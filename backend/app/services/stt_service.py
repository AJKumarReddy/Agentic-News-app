"""Transcription for spoken questions.

The mirror of `tts_service`, with one deliberate difference: nothing is cached.
Every recording is a fresh few hundred kilobytes that will never be sent again,
so a cache here would evict the article entries that keep the site up when a
publisher is unreachable and buy nothing back.

Like synthesis, a failure raises rather than returning empty. An empty string is
a real answer — the reader pressed stop without speaking — and the endpoint
turns it into 204 rather than an error.
"""

import logging

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.core.logging import Timer, log_event

logger = logging.getLogger(__name__)

#: Container types the browser's MediaRecorder actually produces, mapped to the
#: extension the OpenAI SDK infers the format from. Chrome and Firefox record
#: WebM/Opus; Safari only ever produces MP4. The caller's content type is
#: matched against this and nothing else — the filename handed to the API is
#: ours, never a string the caller chose.
AUDIO_EXTENSIONS = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
}


class TranscriptionError(Exception):
    """Transcription failed. Distinct from "nothing was said", which is not."""


_client: AsyncOpenAI | None = None


def get_transcription_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=get_settings().openai_api_key)
    return _client


def transcription_enabled() -> bool:
    settings = get_settings()
    return bool(settings.stt_enabled and settings.openai_api_key)


def audio_extension(content_type: str) -> str | None:
    """The extension for a declared content type, or None if unsupported.

    Browsers append codec parameters — "audio/webm;codecs=opus" — so match on
    the media type alone.
    """
    media_type = content_type.split(";")[0].strip().lower()
    return AUDIO_EXTENSIONS.get(media_type)


async def transcribe(audio: bytes, *, extension: str, model: str | None = None) -> str:
    """Text for one recording.

    Returns "" when the audio held no speech; the caller decides what that
    means. Raises TranscriptionError when the request itself failed.
    """
    if not audio:
        raise TranscriptionError("no audio was uploaded")

    settings = get_settings()
    model = model or settings.stt_model
    client = get_transcription_client()

    # Naming the language skips detection and improves accuracy, but only when
    # a deployment has actually set one — an empty string would be rejected.
    extra = {"language": settings.stt_language} if settings.stt_language else {}

    try:
        with Timer() as timer:
            response = await client.audio.transcriptions.create(
                model=model,
                # a tuple, because the SDK reads the format from the filename
                # and bytes alone carry no name
                file=(f"question.{extension}", audio),
                **extra,
            )
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller as 502
        logger.warning("transcription failed: %s", exc)
        raise TranscriptionError(str(exc)) from exc

    text = (getattr(response, "text", "") or "").strip()
    log_event(
        logger,
        "stt_transcribed",
        bytes=len(audio),
        characters=len(text),
        latency_ms=timer.ms,
    )
    return text
