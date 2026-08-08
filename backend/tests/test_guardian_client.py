import json

import httpx
import pytest

from app.guardian.client import GuardianAPIError, GuardianClient

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
