"""A round-up question must cite a story per article, not one article per story.

The reported symptom was an answer listing seven separate US news stories —
Florida primaries, ICC sanctions, a Disney lawsuit, a threat against Oman —
where every single item carried the citation [1], and [1] was one Guardian
live blog headlined about the first story only. Following any of the other six
citations took the reader to an article that did not report that story.

A live blog is one `article_id` whose body covers the whole day, so a broad
question matched chunk after chunk of it. Nothing capped how much of an answer
one article could supply — diversity was enforced across publishers, never
across articles — so it supplied all of it, and `_chunks_to_evidence` numbers
per article, collapsing six chunks to a single [1].

Two things fix it: no article may contribute more than its share, and a
round-up retrieves breadth (one passage from each of many articles) rather
than depth.
"""

import json
from types import SimpleNamespace

import pytest

from app.agents import graph as graph_module
from app.agents.graph import _chunks_to_evidence, _is_roundup, build_agent_graph
from app.rag.vector_store import ScoredChunk


def chunk(article_id: str, headline: str, chunk_id: int = 1, text: str = "body") -> ScoredChunk:
    return ScoredChunk(
        chunk=SimpleNamespace(
            id=chunk_id, article_id=article_id, headline=headline,
            url=f"https://theguardian.com/{article_id}", published_at=None,
            section="us-news", author="R", text=text,
            source="The Guardian", source_id="guardian",
        ),
        score=1.0,
    )


# ── numbering ──────────────────────────────────────────────────────

def test_one_article_yields_one_citation_number():
    # the reported bug, at its narrowest: six passages of one live blog are
    # one source, so seven listed stories could only ever cite [1]
    liveblog = [chunk("g/liveblog", "Florida primaries – as it happened", i) for i in range(6)]
    evidence, sources = _chunks_to_evidence({"default": liveblog})
    assert len(sources) == 1
    assert {e["n"] for e in evidence} == {1}


def test_distinct_articles_get_distinct_numbers():
    chunks = [chunk(f"g/story{i}", f"Story {i}", i) for i in range(5)]
    evidence, sources = _chunks_to_evidence({"default": chunks})
    assert [s["n"] for s in sources] == [1, 2, 3, 4, 5]
    # each number points at its own article, not at the publisher
    assert [s["url"] for s in sources] == [f"https://theguardian.com/g/story{i}" for i in range(5)]
    assert [e["n"] for e in evidence] == [1, 2, 3, 4, 5]


def test_roundup_evidence_is_trimmed_so_many_articles_fit():
    # `_fill` stops at the first entry over budget, so untrimmed full-text
    # chunks crowd out every article behind them
    chunks = [chunk(f"g/{i}", f"H{i}", i, text="x" * 5000) for i in range(3)]
    evidence, _ = _chunks_to_evidence({"default": chunks}, max_chars=1200)
    assert all(len(e["text"]) == 1200 for e in evidence)


def test_untrimmed_by_default():
    evidence, _ = _chunks_to_evidence({"default": [chunk("g/a", "H", 1, text="x" * 5000)]})
    assert len(evidence[0]["text"]) == 5000


# ── which questions want breadth ───────────────────────────────────

@pytest.mark.parametrize("intent", ["LATEST", "SUMMARY", "TREND"])
def test_roundup_intents(intent):
    assert _is_roundup({"intent": intent})


@pytest.mark.parametrize("intent", ["QA", "FACT", "COMPARISON", "TIMELINE"])
def test_focused_intents_are_not_roundups(intent):
    assert not _is_roundup({"intent": intent})


def test_freshness_alone_makes_a_roundup():
    # "what's happening today" routed as QA still wants a story per citation
    assert _is_roundup({"intent": "QA", "freshness": True})


# ── the graph asks retrieval for breadth ───────────────────────────

@pytest.fixture
def retrieval(monkeypatch):
    """Record the retrieval keyword arguments each turn produces."""
    calls: list[dict] = []

    async def retrieve_rag(session, query, **kwargs):
        calls.append(kwargs)
        return []

    async def fetch_and_index(session, queries, **kwargs):
        return {"found": 0}

    async def search_web(query, **kwargs):
        return []

    monkeypatch.setattr(graph_module.tools, "retrieve_rag", retrieve_rag)
    monkeypatch.setattr(graph_module.tools, "fetch_and_index", fetch_and_index)
    monkeypatch.setattr(graph_module.tools, "search_web", search_web)
    return calls


class Understanding:
    def __init__(self, **payload):
        self.content = json.dumps(
            {"mode": "NEWS", "intent": "QA", "standalone_question": "q",
             "news_query": "q", **payload}
        )

    async def ainvoke(self, prompt):
        return SimpleNamespace(content=self.content)


async def run(query: str, understanding=None):
    graph = build_agent_graph(
        session=None,
        understanding_llm=understanding or Understanding(),
        synthesis_llm=SimpleNamespace(ainvoke=lambda m: _reply()),
    )
    return await graph.ainvoke(
        {"query": query, "conversation_state": {}, "history": [], "steps": []}
    )


async def _reply():
    return SimpleNamespace(content="An answer [1].")


async def test_top_news_retrieves_one_passage_per_article(retrieval):
    from app.core.config import get_settings

    await run(
        "top US news today",
        understanding=Understanding(intent="LATEST", freshness=True),
    )
    assert retrieval[0]["max_per_article"] == 1
    assert retrieval[0]["final_top_k"] == get_settings().rag_roundup_top_k


async def test_a_focused_question_still_retrieves_depth(retrieval):
    await run("what did the report say about the merger")
    # None = the configured default, several passages of the few articles that
    # actually cover it
    assert retrieval[0]["max_per_article"] is None
    assert retrieval[0]["final_top_k"] is None
