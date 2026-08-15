import json

import httpx
import pytest

from app.guardian import client as guardian_module
from app.guardian.client import GuardianAPIError, GuardianClient


@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    """Bypass Redis so these tests exercise HTTP behavior, not cache state."""

    async def miss(key):
        return None

    async def noop(key, value, ttl=None):
        return None

    monkeypatch.setattr(guardian_module, "cache_get", miss)
    monkeypatch.setattr(guardian_module, "cache_set", noop)


@pytest.fixture(autouse=True)
def no_throttle(monkeypatch):
    """The 1.2s inter-call pacing is real behavior, but it would add seconds
    to a suite that makes many calls against a stub transport."""
    monkeypatch.setattr(GuardianClient, "MIN_INTERVAL_SECONDS", 0.0)

SEARCH_PAYLOAD = {
    "response": {
        "status": "ok",
        "total": 2,
        "currentPage": 1,
        "pages": 1,
        "pageSize": 20,
        "results": [
            {
                "id": "technology/2026/aug/07/story-one",
                "webTitle": "Story one",
                "webUrl": "https://www.theguardian.com/technology/2026/aug/07/story-one",
                "webPublicationDate": "2026-08-07T09:00:00Z",
                "sectionName": "Technology",
                "fields": {"headline": "Story one", "bodyText": "Body one."},
                "tags": [],
            },
            {
                "id": "business/2026/aug/06/story-two",
                "webTitle": "Story two",
                "webUrl": "https://www.theguardian.com/business/2026/aug/06/story-two",
                "webPublicationDate": "2026-08-06T09:00:00Z",
                "sectionName": "Business",
                "fields": {"headline": "Story two", "bodyText": "Body two."},
                "tags": [],
            },
        ],
    }
}


def make_client(handler) -> GuardianClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport, base_url=GuardianClient.BASE_URL)
    return GuardianClient(api_key="test-key", client=http)


async def test_search_builds_expected_params():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.url.params))
        return httpx.Response(200, json=SEARCH_PAYLOAD)

    client = make_client(handler)
    result = await client.search(
        query="openai",
        from_date="2026-08-01",
        to_date="2026-08-08",
        section="technology",
        order_by="newest",
        page=2,
        page_size=10,
    )
    assert captured["api-key"] == "test-key"
    assert captured["q"] == "openai"
    assert captured["from-date"] == "2026-08-01"
    assert captured["to-date"] == "2026-08-08"
    assert captured["section"] == "technology"
    assert captured["order-by"] == "newest"
    assert captured["page"] == "2"
    assert captured["page-size"] == "10"
    assert "show-fields" in captured and "body" in captured["show-fields"]
    assert result.total == 2
    assert len(result.articles) == 2
    assert result.articles[0].article_id == "technology/2026/aug/07/story-one"


async def test_author_becomes_contributor_tag():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.url.params))
        return httpx.Response(200, json=SEARCH_PAYLOAD)

    client = make_client(handler)
    await client.search(query="ai", author="Jane Reporter")
    assert captured["tag"] == "profile/janereporter"


async def test_http_error_raises_guardian_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "forbidden"})

    client = make_client(handler)
    with pytest.raises(GuardianAPIError) as excinfo:
        await client.search(query="x")
    assert excinfo.value.status_code == 403


async def test_get_article_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": {"status": "ok"}})

    client = make_client(handler)
    with pytest.raises(GuardianAPIError):
        await client.get_article("technology/2026/aug/07/missing")


async def test_get_article_parses_content():
    payload = {
        "response": {
            "status": "ok",
            "content": json.loads(json.dumps(SEARCH_PAYLOAD["response"]["results"][0])),
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = make_client(handler)
    article = await client.get_article("technology/2026/aug/07/story-one")
    assert article.headline == "Story one"


async def test_identical_searches_hit_the_network_once(monkeypatch):
    """The 500 calls/day developer cap is the binding constraint in production,
    and an uncached search spends one call per page view. Repeat requests must
    be served from Redis instead."""
    store: dict = {}
    calls = 0

    async def get(key):
        return store.get(key)

    async def put(key, value, ttl=None):
        store[key] = value

    monkeypatch.setattr(guardian_module, "cache_get", get)
    monkeypatch.setattr(guardian_module, "cache_set", put)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=SEARCH_PAYLOAD)

    client = make_client(handler)
    first = await client.search(section="technology")
    second = await client.search(section="technology")

    assert calls == 1
    assert [a.article_id for a in first.articles] == [a.article_id for a in second.articles]

    # a different query is a different result and must still go out
    await client.search(section="business")
    assert calls == 2


async def test_cache_key_ignores_the_api_key(monkeypatch):
    """The credential is not part of the identity of a result — including it
    would both leak it into Redis and miss the cache on every key rotation."""
    keys: list[str] = []

    async def get(key):
        keys.append(key)
        return None

    async def put(key, value, ttl=None):
        return None

    monkeypatch.setattr(guardian_module, "cache_get", get)
    monkeypatch.setattr(guardian_module, "cache_set", put)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=SEARCH_PAYLOAD)

    transport = httpx.MockTransport(handler)
    for secret in ("key-one", "key-two"):
        http = httpx.AsyncClient(transport=transport, base_url=GuardianClient.BASE_URL)
        await GuardianClient(api_key=secret, client=http).search(section="technology")

    assert len(keys) == 2 and keys[0] == keys[1]
    assert not any("key-one" in k for k in keys)


async def test_exhausted_retries_keep_the_429(monkeypatch):
    """Callers distinguish 'throttled, try the store' from 'genuinely broken'."""
    monkeypatch.setattr(guardian_module.asyncio, "sleep", lambda *_: _done())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "API rate limit exceeded"})

    client = make_client(handler)
    with pytest.raises(GuardianAPIError) as excinfo:
        await client.search(section="technology")
    assert excinfo.value.status_code == 429


async def _done():
    return None
