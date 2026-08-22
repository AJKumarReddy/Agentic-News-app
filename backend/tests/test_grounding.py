"""Citations must not be manufactured.

The product's promise is that every claim is checkable. Two ways that promise
was breakable from the code rather than from the model, both found by the
evaluation suite:

1. An answer citing nothing had the top three sources attached anyway. Citing
   nothing is exactly what an honest answer looks like when the evidence does
   not support the question — so asked about an invented event, the assistant
   returned citations for it.

2. A marker the model invented — `[7]` when only three sources exist — reached
   the reader as a number with nothing behind it.

Both are asserted here rather than left to the synthesis prompt, because a
guarantee that depends on the model holding it is not a guarantee.
"""

import json
from types import SimpleNamespace

import pytest

from app.agents import graph as graph_module
from app.agents.graph import _strip_markers, build_agent_graph
from app.agents.scope import NO_EVIDENCE_MESSAGE


class RoutesToNews:
    async def ainvoke(self, prompt):
        return SimpleNamespace(
            content=json.dumps(
                {
                    "mode": "NEWS",
                    "intent": "QA",
                    "standalone_question": "what happened",
                    "news_query": "what happened",
                }
            )
        )


def answering(text: str):
    class Synthesis:
        async def ainvoke(self, messages):
            return SimpleNamespace(content=text)

    return Synthesis()


@pytest.fixture
def evidence(monkeypatch):
    """Retrieval that returns real chunks, so synthesis is reached."""

    def give(chunks, sources):
        async def retrieve(*args, **kwargs):
            return chunks

        monkeypatch.setattr(graph_module.tools, "retrieve_rag", retrieve)
        monkeypatch.setattr(graph_module.tools, "fetch_and_index", lambda *a, **k: _noop())
        return sources

    return give


async def _noop(*args, **kwargs):
    return {}


# ── stripping phantom markers ────────────────────────────────────

def test_a_marker_with_no_source_is_removed():
    assert _strip_markers("Rates fell [7].", {7}) == "Rates fell."


def test_stripping_leaves_the_sentence_readable():
    """The reader should not be able to tell a marker was removed."""
    cleaned = _strip_markers("The Fed cut rates [9] , and markets rose [2].", {9})
    assert "[9]" not in cleaned
    assert "[2]" in cleaned
    assert "  " not in cleaned


def test_real_markers_survive():
    assert _strip_markers("Rates fell [1] and rose [2].", set()) == "Rates fell [1] and rose [2]."


# ── the fixed reply when there is nothing to reason from ─────────

def test_the_no_evidence_reply_offers_reasons_rather_than_a_bare_refusal():
    """A reader told only "nothing found" cannot tell a gap in coverage from a
    question about something that never happened."""
    lowered = NO_EVIDENCE_MESSAGE.lower()
    assert "not covered" in lowered or "have not covered" in lowered
    assert "too recent" in lowered
    assert "did not happen" in lowered


def test_the_no_evidence_reply_cites_nothing():
    assert "[1]" not in NO_EVIDENCE_MESSAGE


# ── the fallback that manufactured citations is gone ─────────────

async def test_an_uncited_answer_carries_no_sources(monkeypatch):
    """The defect the evaluation caught: an answer citing nothing used to have
    the top three sources bolted on, so a question about an invented event came
    back with citations attached."""
    sources = [
        {"n": 1, "title": "A", "url": "https://example.com/a"},
        {"n": 2, "title": "B", "url": "https://example.com/b"},
        {"n": 3, "title": "C", "url": "https://example.com/c"},
    ]

    async def retrieve(*args, **kwargs):
        return []

    monkeypatch.setattr(graph_module.tools, "retrieve_rag", retrieve)
    monkeypatch.setattr(graph_module.tools, "fetch_and_index", _noop)
    monkeypatch.setattr(graph_module.tools, "search_web", retrieve)

    graph = build_agent_graph(
        session=None,
        understanding_llm=RoutesToNews(),
        synthesis_llm=answering("I could not find anything on that."),
    )
    final = await graph.ainvoke(
        {
            "query": "the secret 2031 Mars colony",
            "conversation_state": {},
            "history": [],
            "steps": [],
            "sources": sources,
        }
    )
    assert final["sources"] == [], "an uncited answer must not display sources"


async def test_no_retrieval_at_all_reaches_the_fixed_reply(monkeypatch):
    """Given nothing to reason from, the synthesis model still writes something
    plausible. It should not be asked."""

    async def nothing(*args, **kwargs):
        return []

    monkeypatch.setattr(graph_module.tools, "retrieve_rag", nothing)
    monkeypatch.setattr(graph_module.tools, "search_web", nothing)
    monkeypatch.setattr(graph_module.tools, "fetch_and_index", _noop)

    class ExplodingSynthesis:
        async def ainvoke(self, messages):
            raise AssertionError("synthesis must not run with no evidence")

    graph = build_agent_graph(
        session=None, understanding_llm=RoutesToNews(), synthesis_llm=ExplodingSynthesis()
    )
    final = await graph.ainvoke(
        {"query": "the secret 2031 Mars colony", "conversation_state": {}, "history": [], "steps": []}
    )
    assert final["answer"] == NO_EVIDENCE_MESSAGE
    assert final["sources"] == []
