"""The conversation must reach the model that writes the answer.

History was loaded on every turn but only ever used to *resolve* the question
into a standalone one. The synthesis call received a system prompt and the
current question, nothing else — so the assistant could not build on its own
previous answer or say what it had just told you. The chat had no memory below
the resolution step.

Continuity is per conversation: turns come from `get_recent_messages` for one
conversation id, so nothing from another chat can leak in.
"""

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from datetime import datetime, timezone

from app.agents import graph as graph_module
from app.rag.vector_store import ScoredChunk
from app.agents.graph import HISTORY_TURN_CHARS, HISTORY_TURNS, _history_messages, build_agent_graph

HISTORY = [
    {"role": "user", "content": "What is happening with the Post Office inquiry?"},
    {"role": "assistant", "content": "The inquiry published its final report [1]."},
    {"role": "user", "content": "Who was criticised?"},
    {"role": "assistant", "content": "Senior executives were criticised [2][3]."},
]


# ── the turns become real chat messages ───────────────────────────

def test_roles_map_to_message_types():
    messages = _history_messages(HISTORY)
    assert [type(m) for m in messages] == [HumanMessage, AIMessage, HumanMessage, AIMessage]
    assert messages[0].content.startswith("What is happening")


def test_citation_markers_are_stripped():
    """Old numbers refer to that turn's sources and mean nothing now."""
    messages = _history_messages(HISTORY)
    assert messages[1].content == "The inquiry published its final report."
    assert "[2]" not in messages[3].content
    assert messages[3].content == "Senior executives were criticised."


def test_only_the_recent_turns_are_replayed():
    long_history = [{"role": "user", "content": f"turn {i}"} for i in range(20)]
    messages = _history_messages(long_history)
    assert len(messages) == HISTORY_TURNS
    assert messages[-1].content == "turn 19"  # the most recent, not the oldest


def test_long_turns_are_truncated_not_dropped():
    messages = _history_messages([{"role": "assistant", "content": "x" * 5000}])
    assert len(messages) == 1
    assert len(messages[0].content) <= HISTORY_TURN_CHARS + 1  # + the ellipsis


def test_blank_turns_are_skipped():
    assert _history_messages([{"role": "user", "content": "   "}]) == []


def test_no_history_is_no_messages():
    assert _history_messages([]) == []


# ── the messages reach the synthesis call ─────────────────────────

@pytest.fixture
def captured(monkeypatch):
    """Record exactly what the synthesis model is invoked with."""
    seen: dict = {}

    async def retrieve_rag(session, query, **kwargs):
        # One chunk, so the turn reaches synthesis. With none, the graph now
        # answers with the fixed no-evidence reply and never calls the model —
        # correct behaviour, but it would leave nothing here to record.
        return [
            ScoredChunk(
                chunk=SimpleNamespace(
                    id=1,
                    article_id="politics/2026/aug/01/story",
                    headline="A story",
                    url="https://www.theguardian.com/politics/2026/aug/01/story",
                    published_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
                    section="politics",
                    author="R",
                    text="Evidence text for the answer.",
                    source="The Guardian",
                    source_id="guardian",
                ),
                score=0.9,
            )
        ]

    async def fetch_and_index(session, queries, **kwargs):
        return {"found": 0}

    async def search_web(query, **kwargs):
        return []

    monkeypatch.setattr(graph_module.tools, "retrieve_rag", retrieve_rag)
    monkeypatch.setattr(graph_module.tools, "fetch_and_index", fetch_and_index)
    monkeypatch.setattr(graph_module.tools, "search_web", search_web)
    return seen


async def run(query: str, history: list[dict], captured: dict):
    async def synthesis(messages):
        captured["messages"] = messages
        return SimpleNamespace(content="An answer.")

    graph = build_agent_graph(
        session=None,
        understanding_llm=None,  # heuristics; no network
        synthesis_llm=SimpleNamespace(ainvoke=synthesis),
    )
    return await graph.ainvoke(
        {"query": query, "conversation_state": {}, "history": history, "steps": []}
    )


async def test_synthesis_receives_the_conversation(captured):
    await run("what did you just tell me about it?", HISTORY, captured)
    messages = captured["messages"]
    # system prompt, then the thread, then this turn's question
    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[-1], HumanMessage)
    replayed = [m.content for m in messages[1:-1]]
    assert "Who was criticised?" in replayed
    assert "The inquiry published its final report." in replayed


async def test_the_thread_precedes_the_current_question(captured):
    await run("and what about compensation?", HISTORY, captured)
    messages = captured["messages"]
    assert len(messages) == 2 + len(HISTORY)
    # the current turn is last so the model answers it, not an earlier one
    assert "compensation" in messages[-1].content


async def test_a_fresh_conversation_sends_no_thread(captured):
    """Continuity is per chat — a new conversation starts clean."""
    await run("what is happening with the inquiry?", [], captured)
    messages = captured["messages"]
    assert len(messages) == 2
    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[1], HumanMessage)
