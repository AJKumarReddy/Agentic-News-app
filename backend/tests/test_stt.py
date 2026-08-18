"""Transcription of spoken questions.

The endpoint takes raw bytes from anyone holding a client id, so the rules that
matter are the ones bounding what it will accept: which container types, how
large, and what it does when the recording held no speech.
"""

from types import SimpleNamespace

import httpx
import pytest

import app.api.audio as audio_module
import app.api.health as health_module
from app.core.security import BodySizeLimitMiddleware
from app.main import app
from app.services import stt_service

# ── audio_extension ──────────────────────────────────────────────────


def test_codec_parameters_do_not_defeat_the_allowlist():
    """MediaRecorder always appends one, so matching the whole header would
    reject every real recording Chrome produces."""
    assert stt_service.audio_extension("audio/webm;codecs=opus") == "webm"
    assert stt_service.audio_extension("audio/webm") == "webm"


def test_safaris_only_format_is_accepted():
    assert stt_service.audio_extension("audio/mp4") == "mp4"


def test_unsupported_types_are_rejected():
    assert stt_service.audio_extension("application/json") is None
    assert stt_service.audio_extension("") is None
    assert stt_service.audio_extension("text/html;charset=utf-8") is None


def test_matching_is_case_insensitive_and_tolerates_spacing():
    assert stt_service.audio_extension(" AUDIO/WEBM ; codecs=opus") == "webm"


# ── transcribe ───────────────────────────────────────────────────────


class FakeTranscriptions:
    def __init__(self, text: str = "What did the Fed say?"):
        self.text = text
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=self.text)


def fake_client(text: str = "What did the Fed say?"):
    transcriptions = FakeTranscriptions(text)
    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=transcriptions))
    return client, transcriptions


async def test_returns_the_spoken_text(monkeypatch):
    client, calls = fake_client()
    monkeypatch.setattr(stt_service, "get_transcription_client", lambda: client)

    assert await stt_service.transcribe(b"OPUSBYTES", extension="webm") == "What did the Fed say?"


async def test_the_filename_carries_the_format_and_is_ours_not_the_callers(monkeypatch):
    """The SDK infers the container from the name, and a caller-supplied one
    would be an unvalidated string reaching the API."""
    client, calls = fake_client()
    monkeypatch.setattr(stt_service, "get_transcription_client", lambda: client)

    await stt_service.transcribe(b"BYTES", extension="mp4")
    filename, payload = calls.calls[0]["file"]
    assert filename == "question.mp4"
    assert payload == b"BYTES"


async def test_silence_is_an_empty_string_not_an_error(monkeypatch):
    client, _ = fake_client("   ")
    monkeypatch.setattr(stt_service, "get_transcription_client", lambda: client)

    assert await stt_service.transcribe(b"BYTES", extension="webm") == ""


async def test_empty_audio_never_reaches_the_api(monkeypatch):
    client, calls = fake_client()
    monkeypatch.setattr(stt_service, "get_transcription_client", lambda: client)

    with pytest.raises(stt_service.TranscriptionError):
        await stt_service.transcribe(b"", extension="webm")
    assert calls.calls == []


async def test_api_failure_raises_rather_than_returning_silence(monkeypatch):
    class Failing:
        async def create(self, **kwargs):
            raise RuntimeError("upstream exploded")

    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=Failing()))
    monkeypatch.setattr(stt_service, "get_transcription_client", lambda: client)

    with pytest.raises(stt_service.TranscriptionError):
        await stt_service.transcribe(b"BYTES", extension="webm")


async def test_language_is_sent_only_when_configured(monkeypatch):
    client, calls = fake_client()
    monkeypatch.setattr(stt_service, "get_transcription_client", lambda: client)

    monkeypatch.setattr(
        stt_service, "get_settings", lambda: SimpleNamespace(stt_model="m", stt_language="")
    )
    await stt_service.transcribe(b"BYTES", extension="webm")
    assert "language" not in calls.calls[0]

    monkeypatch.setattr(
        stt_service, "get_settings", lambda: SimpleNamespace(stt_model="m", stt_language="en")
    )
    await stt_service.transcribe(b"BYTES", extension="webm")
    assert calls.calls[1]["language"] == "en"


# ── the endpoint ─────────────────────────────────────────────────────


@pytest.fixture
def client(monkeypatch):
    async def fake_transcribe(audio, *, extension, model=None):
        return "What did the Fed say about rate cuts?"

    monkeypatch.setattr(audio_module, "transcription_enabled", lambda: True)
    monkeypatch.setattr(audio_module, "transcribe", fake_transcribe)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def post(client, body=b"OPUSBYTES", content_type="audio/webm;codecs=opus"):
    async with client as c:
        return await c.post(
            "/api/audio/transcribe", content=body, headers={"Content-Type": content_type}
        )


async def test_returns_the_transcript(client):
    response = await post(client)
    assert response.status_code == 200
    assert response.json() == {"text": "What did the Fed say about rate cuts?"}


async def test_an_unsupported_container_is_415(client):
    response = await post(client, content_type="application/json")
    assert response.status_code == 415


async def test_stop_pressed_without_speaking_is_204_not_an_error(client, monkeypatch):
    async def silent(audio, *, extension, model=None):
        return ""

    monkeypatch.setattr(audio_module, "transcribe", silent)
    response = await post(client)
    assert response.status_code == 204
    assert not response.content


async def test_a_transcription_failure_is_502(client, monkeypatch):
    async def failing(audio, *, extension, model=None):
        raise stt_service.TranscriptionError("upstream exploded")

    monkeypatch.setattr(audio_module, "transcribe", failing)
    response = await post(client)
    assert response.status_code == 502


async def test_disabled_deployments_answer_503(client, monkeypatch):
    monkeypatch.setattr(audio_module, "transcription_enabled", lambda: False)
    response = await post(client)
    assert response.status_code == 503


async def test_an_oversized_recording_is_refused_by_the_handler(client, monkeypatch):
    """The middleware catches a declared Content-Length; this is the backstop
    for a chunked upload, which declares none."""
    monkeypatch.setattr(audio_module, "get_settings", lambda: SimpleNamespace(stt_max_bytes=4))
    response = await post(client, body=b"MUCH LONGER THAN FOUR BYTES")
    assert response.status_code == 413


async def test_an_empty_body_is_rejected(client):
    response = await post(client, body=b"")
    assert response.status_code == 400


# ── the per-path body ceiling ────────────────────────────────────────


def test_audio_gets_headroom_while_chat_keeps_its_tight_limit():
    """One global cap could only be useless for chat or impossible for a
    recording; /api/chat must not inherit the audio ceiling."""
    middleware = BodySizeLimitMiddleware(
        None, max_bytes=65536, overrides={"/api/audio/transcribe": 8_388_608}
    )
    assert middleware.limit_for("/api/audio/transcribe") == 8_388_608
    assert middleware.limit_for("/api/chat") == 65536
    assert middleware.limit_for("/api/audio/speech") == 65536


def test_the_most_specific_prefix_wins():
    middleware = BodySizeLimitMiddleware(
        None, max_bytes=100, overrides={"/api/": 200, "/api/audio/transcribe": 900}
    )
    assert middleware.limit_for("/api/audio/transcribe") == 900
    assert middleware.limit_for("/api/news/search") == 200


# ── capabilities ─────────────────────────────────────────────────────


async def test_capabilities_reports_both_halves_of_voice(monkeypatch):
    """The UI renders neither control unless the backend says it can serve it."""
    monkeypatch.setattr(health_module, "speech_enabled", lambda: True)
    monkeypatch.setattr(health_module, "transcription_enabled", lambda: False)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        response = await c.get("/api/capabilities")

    assert response.json() == {"tts": True, "stt": False}
