"""Protections for the endpoints that cost money.

The deployment puts one ALB in front of the backend and routes /api/* to it,
so everything here is reachable from the public internet. Two holes made that
expensive:

  * `client_ip` read the *leftmost* X-Forwarded-For entry, which the caller
    writes. A different value per request meant a fresh rate-limit bucket every
    time, so neither limiter limited anything.
  * `/api/rag/*` and `/api/intent` spend embeddings, publisher quota and LLM
    calls, are called by nothing in the UI, and were open to anyone who knew
    the path.
"""

import httpx
import pytest
from fastapi import Depends, FastAPI

from app.core.config import Settings, get_settings
from app.core.security import RateLimitMiddleware, client_ip, is_expensive, require_admin


@pytest.fixture
def settings(monkeypatch):
    """Swap the cached settings for one this test controls."""
    current = Settings()

    def use(**overrides):
        for key, value in overrides.items():
            setattr(current, key, value)
        get_settings.cache_clear()
        monkeypatch.setattr("app.core.security.get_settings", lambda: current)
        return current

    return use


class FakeRequest:
    def __init__(self, forwarded: str | None = None, peer: str = "10.0.0.1"):
        self.headers = {"x-forwarded-for": forwarded} if forwarded else {}
        self.client = type("C", (), {"host": peer})()


# ── the address the limiter keys on ───────────────────────────────

def test_the_spoofable_end_is_ignored(settings):
    """One ALB appends the real client, so the rightmost entry is ours."""
    settings(trusted_proxy_hops=1)
    assert client_ip(FakeRequest("1.2.3.4, 203.0.113.9")) == "203.0.113.9"


def test_a_forged_header_cannot_move_the_bucket(settings):
    settings(trusted_proxy_hops=1)
    real = "203.0.113.9"
    seen = {
        client_ip(FakeRequest(f"{forged}, {real}"))
        for forged in ("1.1.1.1", "2.2.2.2", "3.3.3.3", "not-an-ip")
    }
    assert seen == {real}  # every forgery lands in the same bucket


def test_two_hops_reads_one_further_in(settings):
    # a CDN in front of the ALB: [forged, client, cdn]
    settings(trusted_proxy_hops=2)
    assert client_ip(FakeRequest("1.2.3.4, 203.0.113.9, 198.51.100.7")) == "203.0.113.9"


def test_a_short_header_never_falls_off_the_left_end(settings):
    """With fewer entries than hops, the leftmost is still ours — returning
    anything further left would hand the bucket back to the caller."""
    settings(trusted_proxy_hops=2)
    assert client_ip(FakeRequest("203.0.113.9")) == "203.0.113.9"


def test_no_proxy_means_the_header_is_ignored(settings):
    settings(trusted_proxy_hops=0)
    assert client_ip(FakeRequest("1.2.3.4, 5.6.7.8", peer="10.0.0.1")) == "10.0.0.1"


def test_the_socket_peer_is_used_without_a_header(settings):
    settings(trusted_proxy_hops=1)
    assert client_ip(FakeRequest(peer="10.0.0.5")) == "10.0.0.5"


async def test_a_forged_header_does_not_defeat_the_limiter(settings):
    settings(trusted_proxy_hops=1)
    app = FastAPI()

    @app.get("/api/data")
    async def data():
        return {"ok": True}

    app.add_middleware(RateLimitMiddleware, limit_per_minute=2, chat_limit_per_minute=2)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        codes = [
            (
                await client.get(
                    "/api/data", headers={"X-Forwarded-For": f"9.9.9.{n}, 203.0.113.9"}
                )
            ).status_code
            for n in range(4)
        ]
    assert codes[:2] == [200, 200]
    assert codes[2:] == [429, 429]


# ── which paths get the stricter budget ───────────────────────────

def test_every_llm_backed_path_shares_the_strict_budget():
    assert is_expensive("/api/chat")
    assert is_expensive("/api/intent")
    assert is_expensive("/api/rag/retrieve")
    # an LLM call per request, straight from the article page
    assert is_expensive("/api/news/article/world/2026/a/intelligence")


def test_ordinary_reads_keep_the_general_budget():
    assert not is_expensive("/api/news/search")
    assert not is_expensive("/api/conversations")
    assert not is_expensive("/api/health")


# ── the operator gate ─────────────────────────────────────────────

def make_gated_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/rag/thing", dependencies=[Depends(require_admin)])
    async def thing():
        return {"ok": True}

    return app


async def call(app, headers=None) -> int:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return (await client.get("/api/rag/thing", headers=headers or {})).status_code


async def test_closed_in_production_when_no_key_is_configured(settings):
    settings(admin_api_key="", environment="production")
    assert await call(make_gated_app()) == 404


async def test_open_in_development_so_the_tooling_still_works(settings):
    settings(admin_api_key="", environment="development")
    assert await call(make_gated_app()) == 200


async def test_a_configured_key_is_required(settings):
    settings(admin_api_key="s3cret", environment="production")
    assert await call(make_gated_app()) == 404
    assert await call(make_gated_app(), {"X-Admin-Key": "wrong"}) == 404
    assert await call(make_gated_app(), {"X-Admin-Key": "s3cret"}) == 200


async def test_the_key_is_required_in_development_too_once_set(settings):
    """Configuring a key means it is enforced everywhere — otherwise a
    development image reachable from outside is still open."""
    settings(admin_api_key="s3cret", environment="development")
    assert await call(make_gated_app()) == 404


async def test_refusal_does_not_advertise_the_endpoint(settings):
    """404, not 403: a 403 confirms there is something there to attack."""
    settings(admin_api_key="s3cret", environment="production")
    transport = httpx.ASGITransport(app=make_gated_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/rag/thing")
    assert response.status_code == 404
    assert "admin" not in response.text.lower()
