"""Speech text preparation, chunking, and the synthesis cache."""

import pytest

from app.core.text import CITATION_MARKER, speakable_text, split_for_speech
from app.services import tts_service


# ── speakable_text ───────────────────────────────────────────────────


def test_strips_citation_markers():
    spoken = speakable_text("Rates rose in March [1]. Analysts disagreed [2][3].")
    assert "[1]" not in spoken
    assert "[" not in spoken
    assert spoken.startswith("Rates rose in March.")


def test_strips_headings_bullets_and_emphasis():
    spoken = speakable_text(
        "## What changed\n\n- **Inflation** fell to 2.1%\n- *Wages* held steady\n"
    )
    assert "##" not in spoken
    assert "**" not in spoken
    assert "- " not in spoken
    assert "Inflation fell to 2.1%" in spoken
    assert "Wages held steady" in spoken


def test_headings_and_bullets_become_sentences():
    """A bullet is a pause to the eye and nothing to the ear. Without a full
    stop the whole list is spoken as one breathless clause."""
    spoken = speakable_text("## What changed\n\n- Inflation eased\n- Unemployment held\n")
    assert "What changed." in spoken
    assert "Inflation eased." in spoken
    assert "Unemployment held." in spoken


def test_a_bullet_that_already_ends_a_clause_gains_nothing():
    spoken = speakable_text("- Rates held steady.\n- Will they cut?\n")
    assert ".." not in spoken
    assert "?." not in spoken


def test_link_keeps_its_label_and_drops_the_url():
    spoken = speakable_text("See [the ruling](https://example.com/a/b) for detail.")
    assert "the ruling" in spoken
    assert "example.com" not in spoken


def test_tables_are_dropped_whole():
    spoken = speakable_text(
        "Coverage split three ways.\n\n"
        "| Outlet | Stories |\n| --- | --- |\n| Guardian | 12 |\n| NYT | 9 |\n\n"
        "The gap narrowed later."
    )
    assert "Guardian | 12" not in spoken
    assert "|" not in spoken
    assert "Coverage split three ways." in spoken
    assert "The gap narrowed later." in spoken


def test_an_answer_that_is_only_a_table_has_nothing_to_say():
    """Empty is a contract, not an accident: the endpoint answers 204 on it
    rather than paying for a request that returns a moment of silence."""
    assert speakable_text("| a | b |\n| --- | --- |\n| 1 | 2 |") == ""
    assert speakable_text("") == ""


def test_snake_case_survives_underscore_emphasis_stripping():
    assert "production_office" in speakable_text("The production_office field was empty.")


def test_citation_marker_is_the_one_the_graph_uses():
    """History replay and speech must agree on what a citation looks like."""
    assert CITATION_MARKER.sub("", "a [1] b") == "a b"


# ── split_for_speech ─────────────────────────────────────────────────


def test_short_text_is_a_single_segment():
    assert split_for_speech("One short sentence.", 100) == ["One short sentence."]


def test_segments_stay_under_the_limit_and_split_between_sentences():
    text = " ".join(f"Sentence number {i} runs on for a while." for i in range(60))
    segments = split_for_speech(text, 200)
    assert len(segments) > 1
    assert all(len(s) <= 200 for s in segments)
    # nothing was split mid-sentence
    assert all(s.endswith(".") for s in segments)


def test_a_single_oversized_sentence_is_hard_split_on_a_space():
    text = "word " * 200
    segments = split_for_speech(text, 100)
    assert all(len(s) <= 100 for s in segments)
    assert "".join(s.replace(" ", "") for s in segments) == text.replace(" ", "")


# ── synthesize ───────────────────────────────────────────────────────


class FakeSpeech:
    def __init__(self, payload: bytes = b"AUDIO"):
        self.payload = payload
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)

        class _Response:
            content = self.payload

        return _Response()


class FakeClient:
    def __init__(self, payload: bytes = b"AUDIO"):
        self.audio = type("Audio", (), {"speech": FakeSpeech(payload)})()


@pytest.fixture
def offline_cache(monkeypatch):
    """An in-memory stand-in for the binary Redis path."""
    store: dict[str, bytes] = {}

    async def get(key):
        return store.get(key)

    async def set_(key, value, ttl=None):
        store[key] = value

    monkeypatch.setattr(tts_service, "cache_get_bytes", get)
    monkeypatch.setattr(tts_service, "cache_set_bytes", set_)
    return store


async def test_synthesize_returns_audio_and_caches_it(monkeypatch, offline_cache):
    client = FakeClient()
    monkeypatch.setattr(tts_service, "get_speech_client", lambda: client)

    audio = await tts_service.synthesize("Rates rose in March.", voice="alloy", model="tts-1")
    assert audio == b"AUDIO"
    assert len(offline_cache) == 1


async def test_a_second_identical_call_spends_nothing(monkeypatch, offline_cache):
    client = FakeClient()
    monkeypatch.setattr(tts_service, "get_speech_client", lambda: client)

    await tts_service.synthesize("Same answer.", voice="alloy", model="tts-1")
    await tts_service.synthesize("Same answer.", voice="alloy", model="tts-1")
    assert len(client.audio.speech.calls) == 1


async def test_cache_key_varies_by_voice_and_model_not_by_conversation():
    a = tts_service.cache_key("text", voice="alloy", model="tts-1", fmt="mp3")
    b = tts_service.cache_key("text", voice="nova", model="tts-1", fmt="mp3")
    c = tts_service.cache_key("text", voice="alloy", model="gpt-4o-mini-tts", fmt="mp3")
    assert a != b != c
    assert a == tts_service.cache_key("text", voice="alloy", model="tts-1", fmt="mp3")


async def test_instructions_only_reach_the_models_that_accept_them(monkeypatch, offline_cache):
    client = FakeClient()
    monkeypatch.setattr(tts_service, "get_speech_client", lambda: client)

    await tts_service.synthesize("One.", model="tts-1")
    assert "instructions" not in client.audio.speech.calls[0]

    await tts_service.synthesize("Two.", model="gpt-4o-mini-tts")
    assert "instructions" in client.audio.speech.calls[1]


async def test_api_failure_raises_rather_than_returning_silence(monkeypatch, offline_cache):
    class Failing:
        async def create(self, **kwargs):
            raise RuntimeError("upstream exploded")

    client = type("C", (), {"audio": type("A", (), {"speech": Failing()})()})()
    monkeypatch.setattr(tts_service, "get_speech_client", lambda: client)

    with pytest.raises(tts_service.SpeechError):
        await tts_service.synthesize("Anything.")


async def test_empty_text_never_reaches_the_api(monkeypatch, offline_cache):
    client = FakeClient()
    monkeypatch.setattr(tts_service, "get_speech_client", lambda: client)

    with pytest.raises(tts_service.SpeechError):
        await tts_service.synthesize("   ")
    assert client.audio.speech.calls == []
