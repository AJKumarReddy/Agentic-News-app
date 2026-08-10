import httpx
import pytest

import app.sources.nyt as nyt_module
from app.guardian.models import NormalizedArticle
from app.services.search_service import interleave
from app.sources.guardian_source import GuardianSource
from app.sources.nyt import NYTSource

NYT_PAYLOAD = {
    "response": {
        "docs": [
            {
                "_id": "nyt://article/abc-123",
                "web_url": "https://www.nytimes.com/2026/08/10/us/politics/story.html",
                "headline": {"main": "Senate advances the bill"},
                "abstract": "The measure cleared a key procedural vote.",
                "lead_paragraph": "WASHINGTON — The Senate voted on Monday to advance the bill.",
                "snippet": "The measure cleared a key procedural vote.",
                "pub_date": "2026-08-10T14:00:00+0000",
                "section_name": "U.S.",
                "byline": {"original": "By Jane Reporter"},
                "keywords": [{"value": "Congress"}, {"value": "Legislation"}],
                "multimedia": [{"url": "images/2026/08/10/thumb.jpg"}],
            }
        ]
    }
}


@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    async def miss(key):
        return None

    async def noop(key, value, ttl=None):
        return None

    monkeypatch.setattr(nyt_module, "cache_get", miss)
    monkeypatch.setattr(nyt_module, "cache_set", noop)


def make_nyt(handler, api_key="test-key") -> NYTSource:
    source = NYTSource(api_key=api_key, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    source.MIN_INTERVAL_SECONDS = 0  # no throttle delay in tests
    return source


async def test_nyt_disabled_without_key():
    source = make_nyt(lambda r: httpx.Response(200, json=NYT_PAYLOAD), api_key="")
    assert source.enabled is False
    assert await source.search("politics") == []


async def test_nyt_normalizes_into_the_shared_model():
    source = make_nyt(lambda r: httpx.Response(200, json=NYT_PAYLOAD))
    articles = await source.search("senate")
    assert len(articles) == 1
    article = articles[0]
    assert article.source == "The New York Times"
    assert article.source_id == "nyt"
    assert article.article_id == "nyt://article/abc-123"
    assert article.url.startswith("https://www.nytimes.com/")
    assert article.author == "Jane Reporter"
    assert article.section == "U.S."
    assert article.production_office == "US"  # NYT is a US publisher
    assert "Congress" in article.tags
    assert article.thumbnail.startswith("https://")
    # body is abstract + lead paragraph; NYT exposes no full text
    assert "cleared a key procedural vote" in article.body_text
    assert "Senate voted on Monday" in article.body_text


async def test_nyt_maps_dates_and_sections_to_api_params():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.url.params))
        return httpx.Response(200, json=NYT_PAYLOAD)

    await make_nyt(handler).search(
        "ai", from_date="2026-08-01", to_date="2026-08-10", section="technology", order_by="newest", page=2
    )
    assert captured["begin_date"] == "20260801"
    assert captured["end_date"] == "20260810"
    assert "Technology" in captured["fq"]
    assert captured["sort"] == "newest"
    assert captured["page"] == "1"  # NYT pages are 0-based


TOP_STORIES_PAYLOAD = {
    "results": [
        {
            "uri": "nyt://article/top-1",
            "url": "https://www.nytimes.com/2026/08/10/us/senate-vote.html",
            "title": "Senate advances the spending bill",
            "abstract": "Lawmakers cleared a procedural hurdle on Monday.",
            "published_date": "2026-08-10T12:00:00-04:00",
            "section": "us",
            "byline": "By Jane Reporter",
            "des_facet": ["Congress"],
            "multimedia": [{"url": "https://static01.nyt.com/images/thumb.jpg"}],
        },
        {
            "uri": "nyt://article/top-2",
            "url": "https://www.nytimes.com/2026/08/10/technology/ai-chips.html",
            "title": "Chipmakers race on AI hardware",
            "abstract": "Demand for accelerators keeps climbing.",
            "published_date": "2026-08-10T09:00:00-04:00",
            "section": "technology",
            "byline": "By Sam Writer",
            "des_facet": ["Artificial Intelligence"],
            "multimedia": [],
        },
    ]
}


async def test_article_search_401_falls_back_to_top_stories():
    """A key valid for Top Stories but not Article Search must still
    contribute reporting rather than dropping NYT entirely."""
    calls = {"search": 0, "top": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "articlesearch" in str(request.url):
            calls["search"] += 1
            return httpx.Response(401, json={"fault": {"faultstring": "Invalid ApiKey"}})
        calls["top"] += 1
        return httpx.Response(200, json=TOP_STORIES_PAYLOAD)

    source = make_nyt(handler)
    articles = await source.search("senate spending")
    assert calls["search"] == 1 and calls["top"] == 1
    assert [a.article_id for a in articles] == ["nyt://article/top-1"]
    assert articles[0].source_id == "nyt"

    # the unavailable endpoint is remembered, not retried on every query
    await source.search("chipmakers")
    assert calls["search"] == 1


async def test_top_stories_normalizes_correctly():
    source = make_nyt(lambda r: httpx.Response(200, json=TOP_STORIES_PAYLOAD))
    articles = await source.top_stories("us-news")
    assert len(articles) == 2
    assert articles[0].headline == "Senate advances the spending bill"
    assert articles[0].author == "Jane Reporter"
    assert articles[0].source == "The New York Times"
    assert articles[0].published_at is not None
    assert "Congress" in articles[0].tags


async def test_top_stories_fallback_returns_nothing_when_off_topic():
    source = make_nyt(lambda r: httpx.Response(200, json=TOP_STORIES_PAYLOAD))
    source._article_search_enabled = False
    # contributing unrelated front-page items would pollute the evidence
    assert await source.search("antarctic ice shelf collapse") == []


async def test_ping_succeeds_on_top_stories_alone():
    def handler(request: httpx.Request) -> httpx.Response:
        if "articlesearch" in str(request.url):
            return httpx.Response(401, json={})
        return httpx.Response(200, json=TOP_STORIES_PAYLOAD)

    assert await make_nyt(handler).ping() is True


async def test_ping_fails_when_key_is_bad_everywhere():
    assert await make_nyt(lambda r: httpx.Response(401, json={})).ping() is False


# ── ownership routing ─────────────────────────────────────────────

def test_sources_claim_their_own_article_ids():
    guardian, nyt = GuardianSource(), NYTSource(api_key="k")
    assert nyt.owns("nyt://article/abc-123")
    assert not guardian.owns("nyt://article/abc-123")
    assert guardian.owns("technology/2026/aug/07/story")
    assert not nyt.owns("technology/2026/aug/07/story")


# ── merge behaviour ───────────────────────────────────────────────

def article(article_id: str, source_id: str) -> NormalizedArticle:
    return NormalizedArticle(
        article_id=article_id,
        headline=article_id,
        url=f"https://example.com/{article_id}",
        source_id=source_id,
    )


def test_interleave_alternates_between_sources():
    guardian = [article("g1", "guardian"), article("g2", "guardian"), article("g3", "guardian")]
    nyt = [article("n1", "nyt"), article("n2", "nyt")]
    merged = [a.article_id for a in interleave([guardian, nyt])]
    # neither publisher is allowed to dominate the top of the list
    assert merged == ["g1", "n1", "g2", "n2", "g3"]


def test_interleave_deduplicates_by_url():
    same = article("dupe", "guardian")
    merged = interleave([[same], [same]])
    assert len(merged) == 1


def test_interleave_handles_an_empty_source():
    guardian = [article("g1", "guardian")]
    merged = [a.article_id for a in interleave([guardian, []])]
    assert merged == ["g1"]


# ── source diversity in retrieval ─────────────────────────────────

def scored(source_id: str, chunk_id: int, score: float):
    from types import SimpleNamespace

    from app.rag.vector_store import ScoredChunk

    return ScoredChunk(chunk=SimpleNamespace(id=chunk_id, source_id=source_id), score=score)


def test_diversity_swaps_in_an_absent_publisher():
    from app.agents.tools import ensure_source_diversity

    selected = [scored("guardian", i, 1.0 - i / 10) for i in range(4)]
    candidates = selected + [scored("nyt", 9, 0.2)]
    result = ensure_source_diversity(selected, candidates)
    sources = [c.chunk.source_id for c in result]
    assert "nyt" in sources
    assert sources.count("guardian") == 3  # relevance still leads
    assert len(result) == 4


def test_diversity_is_a_noop_when_already_mixed():
    from app.agents.tools import ensure_source_diversity

    selected = [scored("guardian", 1, 0.9), scored("nyt", 2, 0.8)]
    assert ensure_source_diversity(selected, selected) == selected


def test_diversity_never_empties_the_dominant_source():
    from app.agents.tools import ensure_source_diversity

    selected = [scored("guardian", 1, 0.9)]
    candidates = selected + [scored("nyt", 2, 0.1)]
    # a single-chunk answer must keep its best match
    assert ensure_source_diversity(selected, candidates) == selected
