import httpx
import pytest

import app.websearch.client as websearch_module
from app.agents.graph import _web_to_evidence
from app.websearch.client import TavilyClient, WebResult


@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    """Bypass Redis so these tests exercise HTTP behavior, not cache state."""

    async def miss(key):
        return None

    async def noop(key, value, ttl=None):
        return None

    monkeypatch.setattr(websearch_module, "cache_get", miss)
    monkeypatch.setattr(websearch_module, "cache_set", noop)

TAVILY_PAYLOAD = {
    "results": [
        {
            "title": "Reuters covers the merger",
            "url": "https://www.reuters.com/business/merger",
            "content": "Reuters reports the merger completed on Monday.",
            "score": 0.91,
            "published_date": "2026-08-09",
        },
        {
            "title": "Analysis piece",
            "url": "https://apnews.com/article/analysis",
            "content": "AP analysis of the deal.",
            "score": 0.72,
        },
    ]
}


def make_client(handler, api_key="tvly-test") -> TavilyClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return TavilyClient(api_key=api_key, client=http)


async def test_disabled_without_api_key():
    client = make_client(lambda r: httpx.Response(200, json=TAVILY_PAYLOAD), api_key="")
    assert client.enabled is False
    assert await client.search("anything") == []


async def test_search_parses_results_and_domains():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(__import__("json").loads(request.content))
        return httpx.Response(200, json=TAVILY_PAYLOAD)

    results = await make_client(handler).search("merger news", max_results=5, days=7)
    assert captured["query"] == "merger news"
    assert captured["days"] == 7
    assert [r.source for r in results] == ["reuters.com", "apnews.com"]
    assert results[0].url == "https://www.reuters.com/business/merger"


async def test_quality_gate_drops_low_signal_domains_and_scores():
    payload = {
        "results": [
            {"title": "Video", "url": "https://www.youtube.com/watch?v=1", "content": "clip", "score": 0.9},
            {"title": "Weak", "url": "https://example.com/a", "content": "x", "score": 0.05},
            {"title": "Empty", "url": "https://example.com/b", "content": "", "score": 0.9},
            {"title": "Good", "url": "https://reuters.com/x", "content": "real reporting", "score": 0.8},
        ]
    }
    results = await make_client(lambda r: httpx.Response(200, json=payload)).search("q")
    assert [r.source for r in results] == ["reuters.com"]


async def test_explicitly_requested_domain_survives_the_filter():
    from app.websearch.client import requested_domains

    payload = {
        "results": [
            {"title": "Clip", "url": "https://www.youtube.com/watch?v=1", "content": "video", "score": 0.9},
            {"title": "News", "url": "https://reuters.com/x", "content": "story", "score": 0.8},
        ]
    }
    client = make_client(lambda r: httpx.Response(200, json=payload))
    assert "youtube.com" in requested_domains("search youtube for related news")
    assert requested_domains("latest AI news") == []

    blocked = await client.search("q")
    assert [r.source for r in blocked] == ["reuters.com"]

    allowed = await client.search("q2", allow_domains=["youtube.com"])
    assert "youtube.com" in [r.source for r in allowed]


async def test_quality_gate_drops_stale_pages_for_news_queries():
    payload = {
        "results": [
            {
                "title": "Old doc",
                "url": "https://developers.google.com/search",
                "content": "docs",
                "score": 0.9,
                "published_date": "2012-05-20",
            },
            {
                "title": "Fresh",
                "url": "https://apnews.com/new",
                "content": "story",
                "score": 0.9,
                "published_date": "2026-08-09",
            },
        ]
    }
    client = make_client(lambda r: httpx.Response(200, json=payload))
    news = await client.search("q", topic="news")
    assert [r.source for r in news] == ["apnews.com"]
    # reference lookups may legitimately surface older pages
    general = await client.search("q2", topic="general")
    assert len(general) == 2


async def test_api_error_returns_empty_not_raises():
    client = make_client(lambda r: httpx.Response(500, text="boom"))
    assert await client.search("x") == []


async def test_timeout_returns_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout")

    assert await make_client(handler).search("x") == []


def test_web_evidence_continues_guardian_numbering():
    sources = [
        {"n": 1, "type": "guardian", "url": "https://www.theguardian.com/a", "headline": "G1"},
        {"n": 2, "type": "guardian", "url": "https://www.theguardian.com/b", "headline": "G2"},
    ]
    evidence = [{"n": 1, "type": "guardian", "group": "default"}]
    results = [
        WebResult(title="W1", url="https://reuters.com/1", content="c", source="reuters.com"),
        WebResult(title="W2", url="https://apnews.com/2", content="c", source="apnews.com"),
    ]
    evidence, sources = _web_to_evidence(results, evidence, sources)

    assert [s["n"] for s in sources] == [1, 2, 3, 4]
    assert [s["type"] for s in sources] == ["guardian", "guardian", "web", "web"]
    assert sources[2]["source"] == "reuters.com"
    # web evidence is grouped separately so the prompt can label it
    assert evidence[-1]["group"] == "web"


def test_web_evidence_skips_duplicate_urls():
    sources = [{"n": 1, "type": "web", "url": "https://reuters.com/1", "headline": "W1"}]
    results = [WebResult(title="dupe", url="https://reuters.com/1", source="reuters.com")]
    evidence, sources = _web_to_evidence(results, [], sources)
    assert len(sources) == 1
