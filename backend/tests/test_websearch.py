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
