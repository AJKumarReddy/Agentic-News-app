"""Ownership rules for conversation delete/list — a client must never be able
to read or delete another client's chats."""

from types import SimpleNamespace

import pytest

from app.database.repositories import ConversationRepository


class FakeSession:
    """Minimal stand-in exercising the repository's ownership checks."""

    def __init__(self, stored: dict):
        self.stored = stored
        self.deleted: list = []

    async def get(self, model, key):
        return self.stored.get(key)

    async def delete(self, obj):
        self.deleted.append(obj)
        self.stored.pop(obj.id, None)


def conversation(cid: str, user_id: str):
    return SimpleNamespace(id=cid, user_id=user_id, title="t")


@pytest.fixture
def repo():
    session = FakeSession(
        {"a": conversation("a", "client-1"), "b": conversation("b", "client-2")}
    )
    return ConversationRepository(session), session


async def test_get_returns_own_conversation(repo):
    repository, _ = repo
    assert await repository.get("a", user_id="client-1") is not None


async def test_get_hides_other_clients_conversation(repo):
    repository, _ = repo
    assert await repository.get("a", user_id="client-2") is None


async def test_delete_own_conversation(repo):
    repository, session = repo
    assert await repository.delete("a", user_id="client-1") is True
    assert "a" not in session.stored


async def test_cannot_delete_other_clients_conversation(repo):
    repository, session = repo
    assert await repository.delete("b", user_id="client-1") is False
    assert "b" in session.stored  # untouched


async def test_delete_missing_conversation_returns_false(repo):
    repository, _ = repo
    assert await repository.delete("does-not-exist", user_id="client-1") is False
