import httpx
import pytest
from fastapi import FastAPI

from app.core.security import (
    ApiKeyMiddleware,
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    TimeoutMiddleware,
    sanitize_user_text,
)


def make_app(**middleware) -> FastAPI:
    app = FastAPI()

    @app.get("/api/health")
    async def health():
        return {"ok": True}

    @app.post("/api/chat")
    async def chat():
        return {"ok": True}

    @app.get("/api/data")
    async def data():
        return {"ok": True}

    if "api_key" in middleware:
        app.add_middleware(ApiKeyMiddleware, api_key=middleware["api_key"])
    if "max_bytes" in middleware:
        app.add_middleware(BodySizeLimitMiddleware, max_bytes=middleware["max_bytes"])
    if "rate" in middleware:
        app.add_middleware(
            RateLimitMiddleware,
            limit_per_minute=middleware["rate"],
            chat_limit_per_minute=middleware.get("chat_rate", middleware["rate"]),
        )
    if middleware.get("headers"):
        app.add_middleware(SecurityHeadersMiddleware)
    if "timeout" in middleware:
        app.add_middleware(TimeoutMiddleware, timeout_seconds=middleware["timeout"])
    return app


def client_for(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_api_key_required_when_configured():
    app = make_app(api_key="secret-key")
    async with client_for(app) as client:
        assert (await client.get("/api/data")).status_code == 401
        assert (await client.get("/api/data", headers={"X-API-Key": "wrong"})).status_code == 401
        assert (await client.get("/api/data", headers={"X-API-Key": "secret-key"})).status_code == 200


async def test_api_key_health_exempt():
    app = make_app(api_key="secret-key")
    async with client_for(app) as client:
        assert (await client.get("/api/health")).status_code == 200


async def test_api_key_disabled_when_empty():
    app = make_app(api_key="")
    async with client_for(app) as client:
        assert (await client.get("/api/data")).status_code == 200


async def test_body_size_limit():
    app = make_app(max_bytes=100)
    async with client_for(app) as client:
        small = await client.post("/api/chat", content=b"x" * 50)
        large = await client.post("/api/chat", content=b"x" * 500)
    assert small.status_code != 413
    assert large.status_code == 413


async def test_rate_limit_enforced_and_chat_stricter():
    app = make_app(rate=5, chat_rate=2)
    async with client_for(app) as client:
        chat_codes = [(await client.post("/api/chat")).status_code for _ in range(3)]
        data_codes = [(await client.get("/api/data")).status_code for _ in range(3)]
    assert chat_codes == [200, 200, 429]  # chat budget = 2/min
    assert 429 not in data_codes  # general budget = 5/min not exhausted


async def test_security_headers_present():
    app = make_app(headers=True)
    async with client_for(app) as client:
        response = await client.get("/api/data")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in response.headers


async def test_timeout_returns_504():
    import asyncio

    app = FastAPI()

    @app.get("/slow")
    async def slow():
        await asyncio.sleep(1.0)
        return {"ok": True}

    app.add_middleware(TimeoutMiddleware, timeout_seconds=0.1)
    async with client_for(app) as client:
        assert (await client.get("/slow")).status_code == 504


def test_sanitize_user_text_bounds_and_cleans():
    assert sanitize_user_text("  hello\x00world  ") == "hello world"
    assert len(sanitize_user_text("a" * 10000)) == 4000
