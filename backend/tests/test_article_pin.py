"""An article pinned to a conversation must be releasable.

The client sends `article_id` only on the "Ask AI" message that opens a chat,
and the conversation state carried it forward unconditionally. So a chat that
started from an article stayed pinned to it forever: every later turn routed to
ARTICLE, and once the id stopped resolving — a rate-limited key, a withdrawn
article — every remaining turn answered "I couldn't find sources for this",
with no way out short of starting a new chat.

Three things break that loop: the lookup is cached and falls back to our own
store, a turn that cannot resolve the article searches instead of giving up,
and the failure releases the pin so the next turn starts clean.
"""

from types import SimpleNamespace

import pytest

from app.agents import graph as graph_module
from app.agents import tools as tools_module
from app.agents.graph import build_agent_graph
from app.agents.understand import refers_to_article, understand
from app.guardian.models import NormalizedArticle
from app.services.chat_service import _updated_state

ARTICLE_ID = "world/2026/aug/01/inquiry"
PINNED = {"active_article_id": ARTICLE_ID, "active_article_headline": "The inquiry reports"}


def article(article_id: str = ARTICLE_ID) -> NormalizedArticle:
    return NormalizedArticle(
        article_id=article_id,
        headline="The inquiry reports",
        url="https://theguardian.com/a",
        section="world",
        author="R",
        body_text="Full body text.",
    )


# ── what counts as an article question ────────────────────────────

def test_pronoun_follow_ups_are_article_questions():
    for message in (
        "what does it say about JLR?",
        "summarise this article",
        "who is the author of this piece?",
        "and what about the fallout?",
    ):
        assert refers_to_article(message), message


def test_self_contained_questions_are_not():
    # an open article does not make every question an article question
    for message in (
        "what is the latest on the US election",
        "give me a summary of the top US news involving the president's order",
        "compare Guardian and NYT coverage of the AI act",
    ):
        assert not refers_to_article(message), message


def test_questions_about_the_chat_are_not_article_questions():
    assert not refers_to_article("summary of this chat")
    assert not refers_to_article("what did we discuss in this conversation")


async def test_unrelated_question_leaves_article_mode(monkeypatch):
    result = await understand(
        "what is the latest on the US election", active_article="The inquiry reports", llm=None
    )
    assert result.mode != "ARTICLE"


async def test_follow_up_still_reaches_the_article():
    result = await understand(
        "what does it say about JLR?", active_article="The inquiry reports", llm=None
    )
    assert result.mode == "ARTICLE"


# ── the lookup: cache, publisher, then our own store ──────────────

@pytest.fixture
def no_cache(monkeypatch):
    store: dict = {}

    async def get(key):
        return store.get(key)

    async def set_(key, value, ttl=None):
        store[key] = value

    monkeypatch.setattr(tools_module, "cache_get", get)
    monkeypatch.setattr(tools_module, "cache_set", set_)
    return store


async def test_repeated_lookups_hit_the_cache(no_cache, monkeypatch):
    """An article chat re-reads one article every turn; without a cache that
    is one publisher request per turn against a rate-limited key."""
    calls = {"n": 0}

    async def counted(article_id):
        calls["n"] += 1
        return article(article_id)

    monkeypatch.setattr(
        tools_module, "source_for_article", lambda aid: SimpleNamespace(get_article=counted)
    )
    for _ in range(4):
        assert await tools_module.get_source_article(ARTICLE_ID) is not None
    assert calls["n"] == 1


async def test_unreachable_publisher_falls_back_to_the_store(no_cache, monkeypatch):
    async def unreachable(article_id):
        raise tools_module.NewsSourceError("rate limited", 429)

    monkeypatch.setattr(
        tools_module, "source_for_article", lambda aid: SimpleNamespace(get_article=unreachable)
    )

    class Repo:
        def __init__(self, session):
            pass

        async def get(self, article_id):
            return SimpleNamespace(article_id=article_id)

    import app.database.repositories as repositories

    monkeypatch.setattr(repositories, "ArticleRepository", Repo)
    monkeypatch.setattr(repositories, "to_normalized", lambda row: article(row.article_id))

    found = await tools_module.get_source_article(ARTICLE_ID, session=object())
    assert found is not None and found.article_id == ARTICLE_ID


# ── a stale pin does not end the turn ─────────────────────────────

@pytest.fixture
def unresolvable(monkeypatch):
    """The pinned article cannot be fetched from anywhere."""
    searched: list[str] = []

    async def missing(article_id, session=None):
        return None

    async def retrieve_rag(session, query, **kwargs):
        searched.append(query)
        return []

    async def fetch_and_index(session, queries, **kwargs):
        return {"found": 0}

    async def search_web(query, **kwargs):
        return []

    monkeypatch.setattr(graph_module.tools, "get_source_article", missing)
    monkeypatch.setattr(graph_module.tools, "retrieve_rag", retrieve_rag)
    monkeypatch.setattr(graph_module.tools, "fetch_and_index", fetch_and_index)
    monkeypatch.setattr(graph_module.tools, "search_web", search_web)
    return searched


async def run(query: str, conversation_state: dict):
    graph = build_agent_graph(
        session=None,
        understanding_llm=None,
        synthesis_llm=SimpleNamespace(ainvoke=lambda m: _reply()),
    )
    return await graph.ainvoke(
        {"query": query, "conversation_state": conversation_state, "history": [], "steps": []}
    )


async def _reply():
    return SimpleNamespace(content="An answer.")


async def test_stale_article_falls_through_to_search(unresolvable):
    final = await run("what does it say about the findings?", dict(PINNED))
    assert final["article_used"] is False
    # the turn searched instead of answering with nothing
    assert unresolvable
    assert "news_evidence" in final["steps"]


async def test_a_resolvable_article_does_not_search(monkeypatch):
    async def found(article_id, session=None):
        return article()

    async def retrieve_rag(session, query, **kwargs):
        raise AssertionError("a resolved article must not trigger a search")

    monkeypatch.setattr(graph_module.tools, "get_source_article", found)
    monkeypatch.setattr(graph_module.tools, "retrieve_rag", retrieve_rag)
    final = await run("what does it say about the findings?", dict(PINNED))
    assert final["article_used"] is True
    assert final["steps"] == ["understand", "article_evidence", "synthesize"]


# ── the pin is released ───────────────────────────────────────────

def test_failed_article_turn_releases_the_pin():
    updated = _updated_state(dict(PINNED), {"mode": "ARTICLE", "article_used": False})
    assert updated["active_article_id"] == ""
    assert updated["active_article_headline"] == ""


def test_successful_article_turn_keeps_the_pin():
    updated = _updated_state(dict(PINNED), {"mode": "ARTICLE", "article_used": True})
    assert updated["active_article_id"] == ARTICLE_ID


def test_the_headline_is_persisted_for_the_next_turn():
    """Nothing wrote this before, so routing asked the model whether a question
    was about "world/2026/aug/01/inquiry" instead of about a headline."""
    updated = _updated_state(
        {"active_article_id": ARTICLE_ID},
        {"mode": "ARTICLE", "article_used": True, "active_article_headline": "The inquiry reports"},
    )
    assert updated["active_article_headline"] == "The inquiry reports"


async def test_the_article_node_reports_its_headline(monkeypatch):
    async def found(article_id, session=None):
        return article()

    monkeypatch.setattr(graph_module.tools, "get_source_article", found)
    final = await run("what does it say about the findings?", dict(PINNED))
    assert final["active_article_headline"] == "The inquiry reports"


async def test_clearing_the_article_empties_both_fields():
    """The reader can release the pin without sending a message — only they
    know whether the conversation has moved on."""
    from app.api.chat import clear_conversation_article

    class Repo:
        def __init__(self, session):
            self.conversation = SimpleNamespace(state=dict(PINNED))

        async def get(self, conversation_id, user_id=""):
            return self.conversation

    class Session:
        def __init__(self):
            self.committed = False

        async def commit(self):
            self.committed = True

    import app.api.chat as chat_api

    repo_holder: dict = {}

    def make_repo(session):
        repo_holder["repo"] = Repo(session)
        return repo_holder["repo"]

    original = chat_api.ConversationRepository
    chat_api.ConversationRepository = make_repo
    try:
        session = Session()
        await clear_conversation_article("c1", session=session, client_id="client-1")
    finally:
        chat_api.ConversationRepository = original

    state = repo_holder["repo"].conversation.state
    assert state["active_article_id"] == ""
    assert state["active_article_headline"] == ""
    assert session.committed


def test_other_modes_leave_the_pin_alone():
    """A web or news detour mid-conversation must not drop the article the
    reader is still looking at."""
    for mode in ("NEWS", "WEB", "BOTH"):
        updated = _updated_state(dict(PINNED), {"mode": mode})
        assert updated["active_article_id"] == ARTICLE_ID, mode
