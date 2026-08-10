"""Security layer.

Middleware stack (outermost → innermost as added in main.py):
  - SecurityHeadersMiddleware   secure response headers on every response
  - BodySizeLimitMiddleware     reject oversized request bodies (413)
  - ApiKeyMiddleware            optional X-API-Key gate for the whole API
  - RateLimitMiddleware         per-IP sliding window, stricter for /api/chat
  - TimeoutMiddleware           bound request processing time (504)

The rate limiter is an in-process sliding window, sufficient for a single
instance behind nginx. For a multi-instance deployment, swap the storage
for Redis (the interface is contained in RateLimiter).
"""

import asyncio
import hmac
import time
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

_SECURE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "X-Permitted-Cross-Domain-Policies": "none",
    # API responses are data, never pages — a restrictive CSP is safe here
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cache-Control": "no-store",
}

EXEMPT_PATHS = {"/api/health"}


def client_ip(request: Request) -> str:
    """Client address, honoring the X-Forwarded-For set by nginx/ALB."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        is_html = response.headers.get("content-type", "").startswith("text/html")
        for key, value in _SECURE_HEADERS.items():
            # the deny-all CSP is for data responses; HTML pages (dev-only
            # Swagger UI) need their scripts/styles
            if key == "Content-Security-Policy" and is_html:
                continue
            response.headers.setdefault(key, value)
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose declared body exceeds the limit (default 64 KB —
    the largest legitimate payload here is a chat message)."""

    def __init__(self, app, max_bytes: int = 65536):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next) -> Response:
        length = request.headers.get("content-length")
        if length is not None:
            try:
                if int(length) > self.max_bytes:
                    return JSONResponse(status_code=413, content={"detail": "Request body too large"})
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})
        return await call_next(request)


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Optional shared-secret gate: when API_KEY is configured, every request
    (except /api/health and CORS preflights) must send it as X-API-Key.

    Suited to private/internal deployments where the caller can hold a
    secret (server-to-server, or an SPA restricted to a trusted audience).
    A key shipped inside a public SPA bundle is discoverable — for a public
    product, replace this with per-user auth (JWT/OAuth). Comparison is
    constant-time to prevent timing attacks.
    """

    def __init__(self, app, api_key: str):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self.api_key or request.method == "OPTIONS" or request.url.path in EXEMPT_PATHS:
            return await call_next(request)
        provided = request.headers.get("x-api-key", "")
        if not hmac.compare_digest(provided.encode(), self.api_key.encode()):
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})
        return await call_next(request)


class RateLimiter:
    SWEEP_EVERY = 1024  # drop idle keys periodically so the dict can't grow forever

    def __init__(self, limit_per_minute: int):
        self.limit = limit_per_minute
        self.window = 60.0
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._calls = 0

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        self._calls += 1
        if self._calls % self.SWEEP_EVERY == 0:
            cutoff = now - self.window
            self._hits = defaultdict(
                deque, {k: v for k, v in self._hits.items() if v and v[-1] > cutoff}
            )
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP sliding window. /api/chat gets its own (stricter) budget since
    each request fans out into Guardian calls, embeddings, and LLM calls."""

    def __init__(self, app, limit_per_minute: int = 30, chat_limit_per_minute: int = 10):
        super().__init__(app)
        self.limiter = RateLimiter(limit_per_minute)
        self.chat_limiter = RateLimiter(chat_limit_per_minute)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in EXEMPT_PATHS or request.method == "OPTIONS":
            return await call_next(request)
        # separate limiter instances already namespace the buckets
        limiter = self.chat_limiter if request.url.path == "/api/chat" else self.limiter
        if not limiter.allow(client_ip(request)):
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please slow down."},
                headers={"Retry-After": "30"},
            )
        return await call_next(request)


class TimeoutMiddleware(BaseHTTPMiddleware):
    """Bound time-to-first-byte. Streaming bodies (SSE) are not affected once
    the response has started."""

    def __init__(self, app, timeout_seconds: float = 120.0):
        super().__init__(app)
        self.timeout_seconds = timeout_seconds

    async def dispatch(self, request: Request, call_next) -> Response:
        try:
            return await asyncio.wait_for(call_next(request), timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            return JSONResponse(status_code=504, content={"detail": "Request timed out"})


def sanitize_user_text(text: str, max_length: int = 4000) -> str:
    """Bound and clean user-supplied text before it reaches prompts or APIs."""
    cleaned = text.replace("\x00", " ").strip()
    return cleaned[:max_length]
