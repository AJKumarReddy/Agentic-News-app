from datetime import datetime

import httpx
import pytest

import app.sources.nyt as nyt_module
from app.guardian.models import NormalizedArticle
from app.services.search_service import merge
from app.sources.guardian_source import GuardianSource
from app.sources.nyt import NYTSource, _extract_thumbnail

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


def test_thumbnail_prefers_article_size_over_the_75px_crop():
    """Article Search's dict shape offers a 75x75 "thumbnail" alongside the
    ~600px "default". Cards render ~360px wide, so picking the crop upscales
    it into mush."""
    assert _extract_thumbnail(
        {
            "default": {"url": "https://static01.nyt.com/a-articleLarge.jpg", "width": 600},
            "thumbnail": {"url": "https://static01.nyt.com/a-thumbStandard.jpg", "width": 75},
        }
    ) == "https://static01.nyt.com/a-articleLarge.jpg"


def test_thumbnail_falls_back_to_the_crop_when_it_is_all_there_is():
    assert _extract_thumbnail(
        {"thumbnail": {"url": "https://static01.nyt.com/a-thumbStandard.jpg", "width": 75}}
    ) == "https://static01.nyt.com/a-thumbStandard.jpg"


def test_thumbnail_skips_super_jumbo_in_the_list_shape():
    """Top Stories leads with a 2048px "Super Jumbo"; the smallest image that
    still covers the card is the right pick."""
    assert _extract_thumbnail(
        [
            {"url": "https://static01.nyt.com/a-superJumbo.jpg", "width": 2048, "type": "image"},
            {"url": "https://static01.nyt.com/a-threeByTwo.jpg", "width": 600, "type": "image"},
            {"url": "https://static01.nyt.com/a-thumbLarge.jpg", "width": 150, "type": "image"},
        ]
    ) == "https://static01.nyt.com/a-threeByTwo.jpg"


def test_thumbnail_takes_the_largest_when_nothing_covers_the_card():
    assert _extract_thumbnail(
        [
            {"url": "https://static01.nyt.com/a-thumbStandard.jpg", "width": 75, "type": "image"},
            {"url": "https://static01.nyt.com/a-thumbLarge.jpg", "width": 150, "type": "image"},
        ]
    ) == "https://static01.nyt.com/a-thumbLarge.jpg"


def test_thumbnail_relative_paths_resolve_to_the_image_cdn():
    """www.nytimes.com/images/... is a 404; the crops live on static01."""
    assert _extract_thumbnail([{"url": "images/2026/08/10/thumb.jpg"}]).startswith(
        "https://static01.nyt.com/images/"
    )


def test_thumbnail_handles_no_multimedia():
    assert _extract_thumbnail(None) == ""
    assert _extract_thumbnail([]) == ""
    assert _extract_thumbnail({}) == ""


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


async def test_top_stories_browse_honours_the_date_range():
    """Top Stories takes no date parameters, so the range is applied to its
    results — otherwise a keyword-free browse ignores the filter entirely."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=TOP_STORIES_PAYLOAD)

    source = make_nyt(handler)
    assert await source.search("", from_date="2026-08-11", to_date="2026-08-12") == []
    inside = await source.search("", from_date="2026-08-10", to_date="2026-08-10")
    assert [a.article_id for a in inside] == ["nyt://article/top-1", "nyt://article/top-2"]


async def test_top_stories_fallback_honours_the_date_range():
    """The 401 fallback must not become a way around the filter."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "articlesearch" in str(request.url):
            return httpx.Response(401, json={"fault": {"faultstring": "Invalid ApiKey"}})
        return httpx.Response(200, json=TOP_STORIES_PAYLOAD)

    source = make_nyt(handler)
    assert await source.search("senate spending", from_date="2026-09-01") == []


def test_within_dates_bounds_are_inclusive_and_drop_undated():
    from datetime import timezone
    from types import SimpleNamespace

    from app.sources.nyt import within_dates

    def article(published):
        return SimpleNamespace(published_at=published)

    items = [
        article(datetime(2026, 3, 1, tzinfo=timezone.utc)),
        article(datetime(2026, 3, 31, tzinfo=timezone.utc)),
        article(datetime(2026, 4, 1, tzinfo=timezone.utc)),
        article(None),
    ]
    kept = within_dates(items, "2026-03-01", "2026-03-31")
    assert len(kept) == 2
    # no range means no filtering, undated included
    assert len(within_dates(items, None, None)) == 4


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

def article(article_id: str, source_id: str, published: str | None = None) -> NormalizedArticle:
    return NormalizedArticle(
        article_id=article_id,
        headline=article_id,
        url=f"https://example.com/{article_id}",
        source_id=source_id,
        published_at=datetime.fromisoformat(published) if published else None,
    )


def test_merge_orders_by_freshness_across_publishers():
    guardian = [article("g1", "guardian", "2026-08-10T09:00:00+00:00")]
    nyt = [
        article("n1", "nyt", "2026-08-10T11:00:00+00:00"),
        article("n2", "nyt", "2026-08-10T10:00:00+00:00"),
    ]
    merged = [a.article_id for a in merge([guardian, nyt])]
    # the freshest wins outright; one publisher may legitimately take the top
    assert merged == ["n1", "n2", "g1"]


def test_merge_compares_across_offset_and_utc():
    # publishers differ on whether they send an offset; mixing naive with
    # aware datetimes raises TypeError on comparison
    guardian = [article("g1", "guardian", "2026-08-10T09:00:00")]
    nyt = [article("n1", "nyt", "2026-08-10T08:00:00+00:00")]
    assert [a.article_id for a in merge([guardian, nyt])] == ["g1", "n1"]


def test_merge_oldest_reverses_and_keeps_undated_last():
    dated = [article("g1", "guardian", "2026-08-10T09:00:00+00:00")]
    older = [article("n1", "nyt", "2026-08-09T09:00:00+00:00")]
    undated = [article("x1", "nyt")]
    merged = [a.article_id for a in merge([dated, older, undated], "oldest")]
    # an absent date must never outrank a real one, in either direction
    assert merged == ["n1", "g1", "x1"]


def test_merge_relevance_round_robins():
    guardian = [article("g1", "guardian"), article("g2", "guardian")]
    nyt = [article("n1", "nyt")]
    # relevance scores aren't comparable across publishers, so preserve
    # each source's own ranking rather than inventing a cross-source order
    assert [a.article_id for a in merge([guardian, nyt], "relevance")] == ["g1", "n1", "g2"]


def test_merge_deduplicates_by_url():
    same = article("dupe", "guardian", "2026-08-10T09:00:00+00:00")
    assert len(merge([[same], [same]])) == 1


def test_merge_handles_an_empty_source():
    guardian = [article("g1", "guardian", "2026-08-10T09:00:00+00:00")]
    assert [a.article_id for a in merge([guardian, []])] == ["g1"]


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


# ── pagination across publishers ───────────────────────────────────

class StubSource:
    def __init__(self, source_id: str, result):
        self.id = source_id
        self._result = result

    async def search_page(self, **kwargs):
        return self._result


async def test_combined_pages_follow_the_deepest_source(monkeypatch):
    from app.services import search_service
    from app.sources.base import SourceResult

    shallow = StubSource("nyt", SourceResult(articles=[article("a", "nyt")], total=8, pages=1))
    deep = StubSource("guardian", SourceResult(articles=[article("b", "guardian")], total=940, pages=47))
    monkeypatch.setattr(search_service, "enabled_sources", lambda: [deep, shallow])

    result = await search_service.search_news(query="x", page=1, page_size=12)
    # paging must continue while any publisher still has more
    assert result.pages == 47
    assert result.total == 948


async def test_combined_pages_are_capped(monkeypatch):
    from app.services import search_service
    from app.sources.base import SourceResult

    huge = StubSource("guardian", SourceResult(articles=[article("a", "guardian")], total=99999, pages=5000))
    monkeypatch.setattr(search_service, "enabled_sources", lambda: [huge])

    result = await search_service.search_news(query="x")
    assert result.pages == search_service.MAX_PAGES


async def test_a_failing_source_does_not_break_pagination(monkeypatch):
    from app.services import search_service
    from app.sources.base import NewsSourceError, SourceResult

    class Failing:
        id = "nyt"

        async def search_page(self, **kwargs):
            raise NewsSourceError("down", 502)

    ok = StubSource("guardian", SourceResult(articles=[article("a", "guardian")], total=30, pages=3))
    monkeypatch.setattr(search_service, "enabled_sources", lambda: [ok, Failing()])

    # nothing stored for the failed source (autouse `offline_store` fixture)
    result = await search_service.search_news(query="x")
    assert result.pages == 3 and result.total == 30
    assert [a.source_id for a in result.articles] == ["guardian"]
    assert result.degraded_sources == []


async def test_unreachable_source_is_served_from_the_store(monkeypatch):
    """A rate-limited publisher shows what we already have, not nothing.

    Developer keys are throttled often enough that dropping the publisher from
    the page would make whole sections look empty.
    """
    from app.services import search_service
    from app.sources.base import NewsSourceError, SourceResult

    class Failing:
        id = "guardian"

        async def search_page(self, **kwargs):
            raise NewsSourceError("Guardian API rate limited", 429)

    async def stored(source, **kwargs):
        assert source.id == "guardian"
        return SourceResult(articles=[article("cached", "guardian")], total=40, pages=4)

    live = StubSource("nyt", SourceResult(articles=[article("fresh", "nyt")], total=12, pages=1))
    monkeypatch.setattr(search_service, "enabled_sources", lambda: [Failing(), live])
    monkeypatch.setattr(search_service, "_from_store", stored)

    result = await search_service.search_news(query="x")

    assert {a.source_id for a in result.articles} == {"guardian", "nyt"}
    # the store backs the pagination too, so the page count does not collapse
    assert result.total == 52 and result.pages == 4
    # ...and the page says so rather than pretending the result is live
    assert result.degraded_sources == ["guardian"]


async def test_live_results_are_written_back_to_the_store(monkeypatch):
    """Ordinary browsing keeps the fallback warm at no extra publisher quota."""
    from app.services import search_service
    from app.sources.base import SourceResult

    saved: list = []

    async def capture(articles):
        saved.extend(articles)

    live = StubSource("guardian", SourceResult(articles=[article("a", "guardian")], total=1, pages=1))
    monkeypatch.setattr(search_service, "enabled_sources", lambda: [live])
    monkeypatch.setattr(search_service, "_remember", capture)

    await search_service.search_news(query="x")
    assert [a.article_id for a in saved] == ["a"]


async def test_failed_source_results_are_not_written_back(monkeypatch):
    """Only live results are persisted — never what we just read from the store,
    which would keep refreshing `retrieved_at` on articles nobody re-fetched."""
    from app.services import search_service
    from app.sources.base import NewsSourceError, SourceResult

    saved: list = []

    class Failing:
        id = "guardian"

        async def search_page(self, **kwargs):
            raise NewsSourceError("down", 429)

    async def stored(source, **kwargs):
        return SourceResult(articles=[article("cached", "guardian")], total=1, pages=1)

    async def capture(articles):
        saved.extend(articles)

    monkeypatch.setattr(search_service, "enabled_sources", lambda: [Failing()])
    monkeypatch.setattr(search_service, "_from_store", stored)
    monkeypatch.setattr(search_service, "_remember", capture)

    await search_service.search_news(query="x")
    assert saved == []


async def test_top_stories_pages_through_the_feed():
    """Top Stories has no server-side paging; slicing its head every time
    served the same articles on every page."""
    feed = {
        "results": [
            {
                "uri": f"nyt://article/f{i}",
                "url": f"https://www.nytimes.com/{i}",
                "title": f"Story {i}",
                "abstract": "abstract",
                "published_date": "2026-08-10T09:00:00-04:00",
                "section": "technology",
                "byline": "By Someone",
            }
            for i in range(10)
        ]
    }
    source = make_nyt(lambda r: httpx.Response(200, json=feed))

    page1 = await source.search("", section="technology", page=1, page_size=4)
    page2 = await source.search("", section="technology", page=2, page_size=4)
    page3 = await source.search("", section="technology", page=3, page_size=4)

    assert [a.article_id for a in page1] == [f"nyt://article/f{i}" for i in range(4)]
    assert [a.article_id for a in page2] == [f"nyt://article/f{i}" for i in range(4, 8)]
    assert not set(a.article_id for a in page1) & set(a.article_id for a in page2)
    assert len(page3) == 2  # feed exhausted, not repeated


async def test_top_stories_reports_finite_pages():
    feed = {
        "results": [
            {"uri": f"nyt://article/g{i}", "url": f"https://nyt.com/{i}", "title": f"T{i}", "abstract": "a"}
            for i in range(10)
        ]
    }
    source = make_nyt(lambda r: httpx.Response(200, json=feed))
    result = await source.search_page("", section="technology", page=1, page_size=4)
    # 10 articles / 4 per page = 3 pages, so Next stops instead of running forever
    assert result.pages == 3
    assert result.total == 10


@pytest.mark.parametrize(
    "slug,stored",
    [
        # the Guardian stores sectionName, NYT stores a title-cased desk
        ("us-news", "US news"),
        ("us-news", "Us"),
        ("world", "World news"),
        ("world", "World"),
        ("technology", "Technology"),
        ("business", "Business"),
        ("politics", "Politics"),
        ("environment", "Environment"),
    ],
)
def test_section_slug_matches_how_publishers_store_it(slug, stored):
    """The fallback filters stored rows by the slug the UI browses with, but
    neither publisher stores the slug — without reconciling them the offline
    page would come back empty for every section."""
    from app.database.repositories import section_variants

    assert stored.lower() in section_variants(slug)


def test_section_variants_do_not_collapse_distinct_sections():
    from app.database.repositories import section_variants

    assert not set(section_variants("world")) & set(section_variants("business"))
