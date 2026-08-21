"""TheNewsAPI adapter and the daily budget that keeps it inside a free plan."""

from datetime import datetime

import httpx
import pytest

import app.sources.quota as quota_module
import app.sources.thenewsapi as thenewsapi_module
from app.sources.base import NewsSourceError
from app.sources.guardian_source import GuardianSource
from app.sources.nyt import NYTSource
from app.sources.thenewsapi import TheNewsAPISource, _pick_category, _published_before

# Trimmed from a real /v1/news/all response: one article, every field the
# adapter reads. Note `keywords` is a comma-separated string, not a list.
PAYLOAD = {
    "meta": {"found": 843, "returned": 1, "limit": 3, "page": 1},
    "data": [
        {
            "uuid": "9ca409ca-d8fe-44b4-b421-c64f8bb57a6a",
            "title": "Experts question new analysis of the 2020 vote",
            "description": "The 24,000 voters in question would not change the outcome.",
            "keywords": "elections, voting, politics",
            "snippet": "This article was originally published by Votebeat, a nonprofit newsroom.",
            "url": "https://www.salon.com/2026/08/21/experts-question-new-analysis/",
            "image_url": "https://www.salon.com/app/uploads/2026/08/voting.jpg",
            "language": "en",
            "published_at": "2026-08-21T10:00:57.000000Z",
            "source": "salon.com",
            "categories": ["general"],
            "locale": "us",
        }
    ],
}


@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    async def miss(key):
        return None

    async def noop(key, value, ttl=None):
        return None

    monkeypatch.setattr(thenewsapi_module, "cache_get", miss)
    monkeypatch.setattr(thenewsapi_module, "cache_set", noop)


@pytest.fixture(autouse=True)
def unlimited_budget(monkeypatch):
    """Quota is exercised deliberately in its own tests; everywhere else it
    would just be a Redis dependency in the way."""

    async def always(source_id, limit):
        return True

    monkeypatch.setattr(thenewsapi_module, "spend", always)


def make_source(handler, api_key="test-key") -> TheNewsAPISource:
    source = TheNewsAPISource(
        api_key=api_key, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    source.MIN_INTERVAL_SECONDS = 0  # no throttle delay in tests
    return source


async def test_disabled_without_key():
    source = make_source(lambda r: httpx.Response(200, json=PAYLOAD), api_key="")
    assert source.enabled is False
    assert await source.search("politics") == []


async def test_normalizes_into_the_shared_model():
    source = make_source(lambda r: httpx.Response(200, json=PAYLOAD))
    articles = await source.search("election")
    assert len(articles) == 1
    article = articles[0]

    assert article.headline == "Experts question new analysis of the 2020 vote"
    assert article.url.startswith("https://www.salon.com/")
    assert article.thumbnail == "https://www.salon.com/app/uploads/2026/08/voting.jpg"
    assert article.published_at == datetime.fromisoformat("2026-08-21T10:00:57+00:00")
    assert article.tags == ["elections", "voting", "politics"]
    assert article.production_office == "US"
    # description and snippet both survive; there is no body text on this API
    assert "24,000 voters" in article.body_text
    assert "Votebeat" in article.body_text


async def test_cites_the_publisher_not_the_aggregator():
    """The whole point of the source field: a reader is told salon.com ran
    this, not that TheNewsAPI relayed it."""
    source = make_source(lambda r: httpx.Response(200, json=PAYLOAD))
    article = (await source.search("election"))[0]
    assert article.source == "salon.com"
    # ...while the machine id still says who fetched it, so the search filter
    # and the stored-article fallback can group by publisher
    assert article.source_id == "thenewsapi"


async def test_category_is_stored_in_the_apps_own_section_vocabulary():
    payload = {**PAYLOAD, "data": [{**PAYLOAD["data"][0], "categories": ["tech"]}]}
    source = make_source(lambda r: httpx.Response(200, json=payload))
    # "tech" is TheNewsAPI's word; everything downstream compares the
    # Guardian's, so a section filter for technology has to find this
    assert (await source.search("chips"))[0].section == "Technology"


async def test_a_section_browse_files_articles_under_the_section_asked_for():
    """Live responses to categories=politics come back tagged
    ["general", "politics"]. Filing those under the catch-all would make the
    section filter look broken on this source alone."""
    payload = {**PAYLOAD, "data": [{**PAYLOAD["data"][0], "categories": ["general", "politics"]}]}
    source = make_source(lambda r: httpx.Response(200, json=payload))
    assert (await source.search("vote", section="politics"))[0].section == "Politics"


def test_category_choice_prefers_the_specific_over_the_catch_all():
    assert _pick_category(["general", "politics"], "politics") == "politics"
    # nothing was asked for, so the informative tag wins over the catch-all
    assert _pick_category(["general", "entertainment"], None) == "entertainment"
    # what was asked for is not there; do not pretend otherwise
    assert _pick_category(["general", "sports"], "politics") == "sports"
    # genuinely only the catch-all
    assert _pick_category(["general"], "politics") == "general"
    assert _pick_category([], "politics") == ""


async def test_ids_are_prefixed_and_claimed_only_by_this_source():
    source = make_source(lambda r: httpx.Response(200, json=PAYLOAD))
    article = (await source.search("election"))[0]
    assert article.article_id == "thenewsapi://9ca409ca-d8fe-44b4-b421-c64f8bb57a6a"

    assert source.owns(article.article_id) is True
    # the scheme is what stops the Guardian's catch-all owns() from claiming it
    assert GuardianSource(client=object()).owns(article.article_id) is False
    assert NYTSource(api_key="k").owns(article.article_id) is False


async def test_maps_dates_sections_and_the_free_tier_limit_to_query_params():
    seen = {}

    def handler(request):
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=PAYLOAD)

    await make_source(handler).search(
        "budget",
        from_date="2026-08-01",
        to_date="2026-08-10",
        section="technology",
        page_size=12,
    )

    assert seen["search"] == "budget"
    assert seen["categories"] == "tech"
    assert seen["language"] == "en"
    assert seen["published_after"] == "2026-08-01"
    # inclusive end date: the API's own bound is exclusive
    assert seen["published_before"] == "2026-08-11"
    # asked for 12, but the free plan rejects anything over 3
    assert seen["limit"] == "3"


async def test_single_day_range_uses_the_exact_parameter():
    seen = {}

    def handler(request):
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=PAYLOAD)

    await make_source(handler).search("vote", from_date="2026-08-21", to_date="2026-08-21")
    assert seen["published_on"] == "2026-08-21"
    assert "published_after" not in seen
    assert "published_before" not in seen


def test_end_of_range_is_pushed_past_the_exclusive_bound():
    assert _published_before("2026-08-10") == "2026-08-11"
    assert _published_before(None) is None
    assert _published_before("not-a-date") is None


async def test_a_keywordless_browse_uses_the_curated_endpoint():
    """`/all` newest-first is the whole firehose, and a live check returned
    three fda.gov boilerplate pages as the top US news. A browse wants /top."""
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=PAYLOAD)

    await make_source(handler).search("", section="technology")

    assert seen["path"] == "/v1/news/top"
    assert seen["params"]["categories"] == "tech"
    # top stories are regional by nature; the edition the app already prefers
    assert seen["params"]["locale"] == "us"
    # /top's value is its own editorial ordering — re-sorting by date would
    # hand back exactly the firehose we switched away from
    assert "sort" not in seen["params"]


async def test_a_keyword_search_stays_on_the_full_index_and_unlocalised():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=PAYLOAD)

    await make_source(handler).search("tariffs")

    assert seen["path"] == "/v1/news/all"
    assert seen["params"]["search"] == "tariffs"
    # pinning a keyword search to US outlets would be a filter; the edition
    # preference is only ever a ranking nudge
    assert "locale" not in seen["params"]
    assert seen["params"]["sort"] == "published_at"


async def test_oldest_does_not_invent_an_ascending_sort():
    """The API has none. Asking for one would silently return newest-first
    anyway; the cross-source merge does the ascending sort instead."""
    seen = {}

    def handler(request):
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=PAYLOAD)

    await make_source(handler).search("vote", order_by="oldest")
    assert seen["sort"] == "published_at"


async def test_search_page_reports_the_total_for_pagination():
    source = make_source(lambda r: httpx.Response(200, json=PAYLOAD))
    result = await source.search_page("election", page_size=3)
    assert result.total == 843
    assert result.pages == 281  # 843 over a 3-article page


async def test_rejected_key_is_a_source_error_not_a_crash():
    source = make_source(lambda r: httpx.Response(401, json={"error": "bad token"}))
    with pytest.raises(NewsSourceError) as exc:
        await source.search("election")
    assert exc.value.status_code == 401


async def test_plan_quota_surfaces_as_a_source_error():
    """402 means the plan's own ceiling was hit before our counter caught up.
    search_service turns any NewsSourceError into the stored-article fallback,
    so this degrades to cached results rather than an empty page."""
    source = make_source(lambda r: httpx.Response(402, json={"error": "limit"}))
    with pytest.raises(NewsSourceError) as exc:
        await source.search("election")
    assert exc.value.status_code == 402


async def test_get_article_unwraps_the_single_article_response():
    def handler(request):
        assert request.url.path.endswith("/uuid/9ca409ca-d8fe-44b4-b421-c64f8bb57a6a")
        return httpx.Response(200, json=PAYLOAD["data"][0])

    source = make_source(handler)
    article = await source.get_article("thenewsapi://9ca409ca-d8fe-44b4-b421-c64f8bb57a6a")
    assert article is not None
    assert article.source == "salon.com"


# ── the daily budget ─────────────────────────────────────────────────


class FakeRedis:
    """Enough of the Redis surface for the counter, plus a switch to make it
    fail the way an outage does."""

    def __init__(self, broken=False):
        self.values: dict[str, int] = {}
        self.expiries: dict[str, int] = {}
        self.broken = broken

    async def incr(self, key):
        if self.broken:
            raise ConnectionError("redis is down")
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    async def expire(self, key, ttl):
        self.expiries[key] = ttl

    async def get(self, key):
        if self.broken:
            raise ConnectionError("redis is down")
        return self.values.get(key)


@pytest.fixture
def fake_redis(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(quota_module, "get_redis", lambda: redis)
    return redis


async def test_budget_refuses_the_call_that_would_exceed_it(fake_redis):
    assert await quota_module.spend("thenewsapi", 3) is True
    assert await quota_module.spend("thenewsapi", 3) is True
    assert await quota_module.spend("thenewsapi", 3) is True
    assert await quota_module.spend("thenewsapi", 3) is False
    assert await quota_module.spent_today("thenewsapi") == 4


async def test_counter_expires_so_a_days_spend_cannot_outlive_the_day(fake_redis):
    await quota_module.spend("thenewsapi", 10)
    assert list(fake_redis.expiries.values()) == [quota_module._TTL_SECONDS]
    # the expiry is set once, on the first spend of the day
    await quota_module.spend("thenewsapi", 10)
    assert len(fake_redis.expiries) == 1


async def test_ingestion_stops_at_the_reserve_while_search_keeps_going(monkeypatch):
    """The reason the reserve exists: the five-minute scheduler must not be
    able to drink the whole day before anyone opens the site."""
    redis = FakeRedis()
    monkeypatch.setattr(quota_module, "get_redis", lambda: redis)

    source = TheNewsAPISource(api_key="test-key")
    monkeypatch.setattr(
        thenewsapi_module.get_settings(), "thenewsapi_daily_budget", 100, raising=False
    )
    monkeypatch.setattr(
        thenewsapi_module.get_settings(), "thenewsapi_interactive_reserve", 40, raising=False
    )

    token = quota_module.background_ingest.set(True)
    try:
        assert source._budget() == 60
        redis.values[f"quota:thenewsapi:{quota_module._today()}"] = 60
        # background is done at 60...
        assert await quota_module.spend("thenewsapi", source._budget()) is False
    finally:
        quota_module.background_ingest.reset(token)

    # ...but a reader searching still has the reserve to spend
    assert source._budget() == 100
    assert await quota_module.spend("thenewsapi", source._budget()) is True


async def test_budget_fails_open_when_redis_is_unreachable(monkeypatch):
    """A cache outage must not mute the publisher. Overspending is answered by
    the API with a 402, which already degrades gracefully."""
    monkeypatch.setattr(quota_module, "get_redis", lambda: FakeRedis(broken=True))
    assert await quota_module.spend("thenewsapi", 1) is True
    assert await quota_module.spent_today("thenewsapi") == 0


async def test_a_zero_budget_is_always_refused(monkeypatch):
    """How the reserve turns background traffic off outright when someone sets
    reserve >= budget."""
    monkeypatch.setattr(quota_module, "get_redis", lambda: FakeRedis())
    assert await quota_module.spend("thenewsapi", 0) is False


async def test_ping_does_not_spend_a_request(monkeypatch):
    """Health is polled all day on a 60s cache; a real probe would cost ~1400
    requests against a budget of 100 and take the source down by itself."""
    called = False

    def handler(request):
        nonlocal called
        called = True
        return httpx.Response(200, json=PAYLOAD)

    monkeypatch.setattr(quota_module, "get_redis", lambda: FakeRedis())
    source = make_source(handler)
    assert await source.ping() is True
    assert called is False
