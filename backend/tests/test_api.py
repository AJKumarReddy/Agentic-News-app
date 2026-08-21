import httpx
import pytest

import app.api.health as health_module
import app.api.news as news_module
from app.guardian.models import GuardianSearchResult, NormalizedArticle
from app.main import app


@pytest.fixture
def client():
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_health_reports_component_status(client, monkeypatch):
    async def ok():
        return True

    async def cache_get(key):
        return {"guardian": "available", "nyt": "available", "thenewsapi": "available"}

    monkeypatch.setattr(health_module, "check_db", ok)
    monkeypatch.setattr(health_module, "check_vector_extension", ok)
    monkeypatch.setattr(health_module, "check_redis", ok)
    monkeypatch.setattr(health_module, "cache_get", cache_get)

    async with client as c:
        response = await c.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["database"] == "connected"
    assert body["vector_database"] == "connected"
    # every configured publisher is reported individually
    assert body["sources"]["guardian"] == "available"
    assert body["sources"]["nyt"] == "available"
    assert body["sources"]["thenewsapi"] == "available"


async def test_health_degraded_without_db(client, monkeypatch):
    async def fail():
        return False

    async def ok():
        return True

    async def cache_get(key):
        return {"guardian": "available"}

    monkeypatch.setattr(health_module, "check_db", fail)
    monkeypatch.setattr(health_module, "check_vector_extension", fail)
    monkeypatch.setattr(health_module, "check_redis", ok)
    monkeypatch.setattr(health_module, "cache_get", cache_get)

    async with client as c:
        response = await c.get("/api/health")
    assert response.json()["status"] == "degraded"


async def test_news_search_returns_articles(client, monkeypatch):
    async def fake_search(**kwargs):
        assert kwargs["query"] == "openai"
        assert kwargs["order_by"] == "newest"
        return GuardianSearchResult(
            total=1,
            articles=[
                NormalizedArticle(
                    article_id="technology/2026/aug/07/a",
                    headline="A story",
                    url="https://www.theguardian.com/technology/2026/aug/07/a",
                )
            ],
        )

    monkeypatch.setattr(news_module, "search_news", fake_search)
    async with client as c:
        response = await c.get("/api/news/search", params={"q": "openai", "order_by": "newest"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["articles"][0]["headline"] == "A story"


async def test_news_search_validates_order_by(client):
    async with client as c:
        response = await c.get("/api/news/search", params={"q": "x", "order_by": "bogus"})
    assert response.status_code == 422


async def test_news_search_validates_date_format(client):
    async with client as c:
        response = await c.get("/api/news/search", params={"from_date": "07-08-2026"})
    assert response.status_code == 422


async def test_chat_requires_message(client):
    async with client as c:
        response = await c.post("/api/chat", json={"message": ""})
    assert response.status_code == 422
