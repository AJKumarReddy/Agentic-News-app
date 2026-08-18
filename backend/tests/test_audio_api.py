"""Ownership and availability rules for answer playback.

The endpoint must never let one client hear another client's chat, and must
never become a way to spend the OpenAI key on arbitrary text.
"""

from types import SimpleNamespace

import httpx
import pytest

import app.api.audio as audio_module
from app.api.chat import client_id_header
from app.database.session import get_session
from app.main import app


class FakeRepo:
    """Stands in for ConversationRepository with the same ownership contract."""

    conversations = {"conv-1": SimpleNamespace(id="conv-1", user_id="client-1", state={})}
    messages = {
        1: SimpleNamespace(id=1, conversation_id="conv-1", role="assistant",
                           content="Rates rose in March [1]."),
        2: SimpleNamespace(id=2, conversation_id="conv-1", role="user", content="what changed?"),
        3: SimpleNamespace(id=3, conversation_id="conv-1", role="assistant",
                           content="| a | b |\n| --- | --- |\n| 1 | 2 |"),
        9: SimpleNamespace(id=9, conversation_id="other-conv", role="assistant", content="Elsewhere."),
    }

    def __init__(self, session):
        pass

    async def get(self, conversation_id, user_id=""):
        conversation = self.conversations.get(conversation_id)
        if conversation is None or conversation.user_id != user_id:
            return None
        return conversation

    async def get_message(self, conversation_id, message_id):
        message = self.messages.get(message_id)
        if message is None or message.conversation_id != conversation_id:
            return None
        return message


@pytest.fixture
def client(monkeypatch):
    async def fake_session():
        yield None

    async def fake_synthesize(text, **kwargs):
        return b"ID3AUDIOBYTES"

    monkeypatch.setattr(audio_module, "ConversationRepository", FakeRepo)
    monkeypatch.setattr(audio_module, "synthesize", fake_synthesize)
    monkeypatch.setattr(audio_module, "speech_enabled", lambda: True)

    app.dependency_overrides[get_session] = fake_session
    app.dependency_overrides[client_id_header] = lambda: "client-1"
    yield httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    app.dependency_overrides.clear()


def body(message_id=1, conversation_id="conv-1"):
    return {"conversation_id": conversation_id, "message_id": message_id}


async def test_returns_audio_for_an_owned_assistant_message(client):
    async with client as c:
        response = await c.post("/api/audio/speech", json=body())
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == b"ID3AUDIOBYTES"


async def test_explicit_cache_control_survives_the_security_headers(client):
    """SecurityHeadersMiddleware sets no-store with setdefault, so a response
    that states its own caching keeps it — replays cost no round trip."""
    async with client as c:
        response = await c.post("/api/audio/speech", json=body())
    assert response.headers["cache-control"] == "private, max-age=86400"


async def test_another_clients_conversation_is_invisible(client):
    app.dependency_overrides[client_id_header] = lambda: "client-2"
    async with client as c:
        response = await c.post("/api/audio/speech", json=body())
    assert response.status_code == 404


async def test_unknown_message_is_404(client):
    async with client as c:
        response = await c.post("/api/audio/speech", json=body(message_id=404))
    assert response.status_code == 404


async def test_message_from_another_conversation_is_404(client):
    """Ids are sequential integers, so scoping by conversation is what stops
    a caller walking into somebody else's chat by guessing one."""
    async with client as c:
        response = await c.post("/api/audio/speech", json=body(message_id=9))
    assert response.status_code == 404


async def test_user_messages_are_never_spoken(client):
    async with client as c:
        response = await c.post("/api/audio/speech", json=body(message_id=2))
    assert response.status_code == 404


async def test_answer_with_nothing_speakable_returns_204(client):
    async with client as c:
        response = await c.post("/api/audio/speech", json=body(message_id=3))
    assert response.status_code == 204
    assert not response.content


async def test_disabled_speech_reports_unavailable(client, monkeypatch):
    monkeypatch.setattr(audio_module, "speech_enabled", lambda: False)
    async with client as c:
        response = await c.post("/api/audio/speech", json=body())
    assert response.status_code == 503


async def test_synthesis_failure_is_a_bad_gateway(client, monkeypatch):
    async def failing(text, **kwargs):
        raise audio_module.SpeechError("upstream exploded")

    monkeypatch.setattr(audio_module, "synthesize", failing)
    async with client as c:
        response = await c.post("/api/audio/speech", json=body())
    assert response.status_code == 502
