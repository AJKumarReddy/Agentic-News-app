"""A requested date range must reach retrieval intact and stay enforced.

The reported symptom was answers containing articles from outside the period
asked about. There were several independent causes, each covered here:

  * relaxation rebuilt the filter from scratch and lost `to_date`, so widening
    the start silently removed the end bound;
  * relaxation ran even for a range the user stated, not just for the window we
    infer behind "latest";
  * TIMELINE and COMPARISON rebuilt filters from a subset of the slots;
  * the web leg used a flat 30-day window regardless of what was asked.
"""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.agents import graph as graph_module
from app.agents.graph import _window_label, build_agent_graph
from app.agents.understand import understand
from app.rag.vector_store import RetrievalFilters, ScoredChunk

TODAY = date.today()


def chunk(published: datetime) -> ScoredChunk:
    return ScoredChunk(
        chunk=SimpleNamespace(
            id=1, article_id="a1", headline="H", url="https://theguardian.com/a1",
            published_at=published, section="world", author="R", text="body",
            source="The Guardian", source_id="guardian",
        ),
        score=1.0,
    )


@pytest.fixture
def retrieval(monkeypatch):
    """Record the filters every retrieval call receives; return nothing."""
    seen: list[RetrievalFilters] = []
    hits: list[ScoredChunk] = []

    async def retrieve_rag(session, query, filters=None, **kwargs):
        seen.append(filters)
        return list(hits)

    async def fetch_and_index(session, queries, **kwargs):
        return {"found": 0}

    async def search_web(query, **kwargs):
        return []

    monkeypatch.setattr(graph_module.tools, "retrieve_rag", retrieve_rag)
    monkeypatch.setattr(graph_module.tools, "fetch_and_index", fetch_and_index)
    monkeypatch.setattr(graph_module.tools, "search_web", search_web)
    return SimpleNamespace(filters=seen, hits=hits)


class Understanding:
    """Understanding model returning a fixed routing payload."""

    def __init__(self, **payload):
        import json

        self.content = json.dumps({"mode": "NEWS", "intent": "QA",
                                   "standalone_question": "q", "news_query": "q", **payload})

    async def ainvoke(self, prompt):
        return SimpleNamespace(content=self.content)


async def run(query: str, understanding=None, **initial):
    answering = SimpleNamespace(ainvoke=lambda m: _reply())
    graph = build_agent_graph(
        session=None,
        understanding_llm=understanding or Understanding(),
        synthesis_llm=answering,
    )
    return await graph.ainvoke(
        {"query": query, "conversation_state": {}, "history": [], "steps": [], **initial}
    )


async def _reply():
    return SimpleNamespace(content="An answer [1].")


# ── the range survives into the SQL filters ───────────────────────

MARCH = {"from_date": "2026-03-01", "to_date": "2026-03-31"}


async def test_stated_range_reaches_retrieval(retrieval):
    await run(
        "what was reported between 2026-03-01 and 2026-03-31",
        understanding=Understanding(**MARCH),
    )
    applied = retrieval.filters[0]
    assert applied.from_date.date() == date(2026, 3, 1)
    assert applied.to_date.date() == date(2026, 3, 31)


async def test_timeline_keeps_its_end_date(retrieval):
    # the TIMELINE branch used to forward only from_date
    await run(
        "timeline of the inquiry from 2026-03-01 to 2026-03-31",
        understanding=Understanding(intent="TIMELINE", entities=["inquiry"], **MARCH),
    )
    assert retrieval.filters[0].to_date is not None
    assert retrieval.filters[0].to_date.date() == date(2026, 3, 31)


async def test_comparison_keeps_the_section(retrieval):
    # the COMPARISON branch used to rebuild filters from dates alone
    await run(
        "compare Meta and Apple in technology during 2026-03-01 to 2026-03-31",
        understanding=Understanding(
            intent="COMPARISON", entities=["Meta", "Apple"], section="technology", **MARCH
        ),
    )
    assert retrieval.filters[0].sections == ["technology"]
    assert retrieval.filters[0].to_date.date() == date(2026, 3, 31)


def test_filter_bounds_are_utc_aware():
    # naive bounds are read in the DB session's timezone, shifting the window
    filters = RetrievalFilters.from_iso("2026-03-01", "2026-03-31")
    assert filters.from_date.tzinfo is not None
    assert filters.to_date.tzinfo is not None
    assert filters.from_date == datetime(2026, 3, 1, tzinfo=timezone.utc)
    assert filters.to_date.date() == date(2026, 3, 31)


# ── a stated range is never widened ───────────────────────────────

async def test_stated_range_is_not_widened_when_empty(retrieval):
    final = await run(
        "what was reported between 2026-03-01 and 2026-03-31",
        understanding=Understanding(**MARCH),
    )
    # exactly one retrieval: no relaxation ladder ran
    assert len(retrieval.filters) == 1
    assert final["sources"] == []
    assert final["notice"] == "No newsroom coverage in 2026-03-01 to 2026-03-31"


async def test_inferred_window_still_widens(retrieval):
    # "latest" implies a 7-day window we chose ourselves — widening it is fine
    final = await run("latest news on the inquiry")
    assert len(retrieval.filters) > 1
    assert final["mode"] == "NEWS"


async def test_widening_keeps_the_end_bound(retrieval):
    """Widening the start must not drop `to_date`."""
    await run("latest news on the inquiry")
    widened = retrieval.filters[1]
    original = retrieval.filters[0]
    assert widened.from_date < original.from_date
    assert widened.to_date == original.to_date


async def test_widening_reports_itself(retrieval, monkeypatch):
    """The widened window is surfaced as UI metadata, not buried."""

    async def empty_then_hit(session, query, filters=None, **kwargs):
        retrieval.filters.append(filters)
        return [] if len(retrieval.filters) == 1 else [chunk(datetime.now(timezone.utc))]

    monkeypatch.setattr(graph_module.tools, "retrieve_rag", empty_then_hit)
    final = await run("latest news on the inquiry")
    assert final["notice"].startswith("Results from")
    assert final["sources"]


# ── the window is described to the model, not hidden from it ──────

def test_window_label_reads_naturally():
    assert _window_label({"from_date": "2026-03-01", "to_date": "2026-03-31"}) == (
        "2026-03-01 to 2026-03-31"
    )
    assert _window_label({"from_date": "2026-03-01", "to_date": "2026-03-01"}) == "2026-03-01"
    assert _window_label({"from_date": "2026-03-01"}) == "since 2026-03-01"
    assert _window_label({"to_date": "2026-03-31"}) == "up to 2026-03-31"
    assert _window_label({}) == "that period"


# ── model-supplied dates are validated ────────────────────────────

async def test_unparseable_model_date_is_dropped():
    result = await understand("news on the inquiry", llm=Understanding(from_date="last week"))
    assert result.from_date is None  # would have raised inside retrieval


async def test_impossible_model_date_is_dropped():
    result = await understand("news on the inquiry", llm=Understanding(from_date="2026-13-45"))
    assert result.from_date is None


async def test_future_model_date_is_dropped():
    ahead = (TODAY + timedelta(days=30)).isoformat()
    result = await understand("news on the inquiry", llm=Understanding(from_date=ahead))
    assert result.from_date is None  # a future window matches nothing


async def test_inverted_model_range_is_corrected():
    result = await understand(
        "coverage between 5 and 20 January 2026",
        llm=Understanding(from_date="2026-01-20", to_date="2026-01-05"),
    )
    assert result.from_date == "2026-01-05"
    assert result.to_date == "2026-01-20"


async def test_model_range_is_explicit_only_when_a_date_was_written():
    written = await understand(
        "coverage in March 2026", llm=Understanding(from_date="2026-03-01", to_date="2026-03-31")
    )
    assert written.date_explicit is True

    guessed = await understand(
        "what is happening with the inquiry",
        llm=Understanding(from_date="2026-03-01", to_date="2026-03-31"),
    )
    assert guessed.date_explicit is False


async def test_freshness_window_is_never_explicit():
    result = await understand("latest on the inquiry", llm=None)
    assert result.from_date is not None
    assert result.date_explicit is False
