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

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings

_SECURE_HEADERS = {
    # TLS terminates at the ALB, so this response travels to it over plain
    # HTTP — but the ALB forwards the header to the browser over HTTPS, which
    # is where it takes effect. Without it, the very first request of a visit
    # can still go out in cleartext before the :80 → :443 redirect answers.
    # Browsers ignore the header on a plain-HTTP page, so local dev is
    # unaffected. No `preload` — that is a one-way commitment to the HSTS
    # preload list, including every subdomain, and should be a deliberate act.
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
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

#: Paths whose every request costs an LLM call, a publisher request or an
#: embedding. They share the stricter budget: previously only "/api/chat"
#: matched exactly, so article intelligence — an LLM call per request, straight
#: from the article page — sat on the general limit alongside static reads.
_EXPENSIVE_PATHS = {"/api/chat", "/api/intent"}
_EXPENSIVE_SUFFIXES = ("/intelligence",)


#: Answer playback. Kept out of `_EXPENSIVE_PATHS` on purpose: sharing the chat
#: bucket would make every turn cost two requests against one budget once
#: autoplay is on, halving usable chat throughput — and the resulting 429 reads
#: to the user as a broken chat rather than as throttled audio.
_AUDIO_PREFIX = "/api/audio/"


def is_expensive(path: str) -> bool:
    return path in _EXPENSIVE_PATHS or path.startswith("/api/rag/") or path.endswith(
        _EXPENSIVE_SUFFIXES
    )


def is_audio(path: str) -> bool:
    return path.startswith(_AUDIO_PREFIX)


def client_ip(request: Request) -> str:
    """Client address, read from the trusted end of X-Forwarded-For.

    A proxy *appends* the address it received the connection from, so the
    rightmost entries are written by our own infrastructure and the leftmost
    by the caller. Reading the leftmost — as this did — meant anyone could
    send `X-Forwarded-For: <anything>` and land in a fresh rate-limit bucket
    on every request, which made both limiters decorative.

    `trusted_proxy_hops` says how many entries on the right we put there
    ourselves; the last of those is the real client. Set it to 0 when the
    process is reachable directly, and the header is ignored entirely.
    """
    hops = get_settings().trusted_proxy_hops
    if hops > 0:
        forwarded = [
            part.strip()
            for part in request.headers.get("x-forwarded-for", "").split(",")
            if part.strip()
        ]
        if forwarded:
            # count in from the right; never fall off the left end, or a short
            # header would hand the caller control of the bucket again
            return forwarded[max(0, len(forwarded) - hops)]
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
    the largest legitimate text payload here is a chat message).

    `overrides` raises the ceiling for specific path prefixes. Uploaded audio is
    three orders of magnitude larger than any JSON this API takes, and a single
    global limit would have to be either useless for chat or impossible for a
    recording. Raising it per path keeps /api/chat tight.
    """

    def __init__(self, app, max_bytes: int = 65536, overrides: dict[str, int] | None = None):
        super().__init__(app)
        self.max_bytes = max_bytes
        # longest prefix first, so a specific path wins over a broader one
        self.overrides = sorted((overrides or {}).items(), key=lambda kv: -len(kv[0]))

    def limit_for(self, path: str) -> int:
        for prefix, limit in self.overrides:
            if path.startswith(prefix):
                return limit
        return self.max_bytes

    async def dispatch(self, request: Request, call_next) -> Response:
        length = request.headers.get("content-length")
        if length is not None:
            try:
                if int(length) > self.limit_for(request.url.path):
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
    """Per-IP sliding window. Paths that fan out into publisher calls,
    embeddings or LLM calls get their own, stricter budget — see
    `is_expensive`."""

    def __init__(
        self,
        app,
        limit_per_minute: int = 30,
        chat_limit_per_minute: int = 10,
        audio_limit_per_minute: int = 20,
    ):
        super().__init__(app)
        self.limiter = RateLimiter(limit_per_minute)
        self.chat_limiter = RateLimiter(chat_limit_per_minute)
        self.audio_limiter = RateLimiter(audio_limit_per_minute)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in EXEMPT_PATHS or request.method == "OPTIONS":
            return await call_next(request)
        # separate limiter instances already namespace the buckets
        path = request.url.path
        if is_audio(path):
            limiter = self.audio_limiter
        elif is_expensive(path):
            limiter = self.chat_limiter
        else:
            limiter = self.limiter
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


async def require_admin(request: Request) -> None:
    """Gate operator-only endpoints.

    `/api/rag/*` and `/api/intent` spend publisher quota and OpenAI credit on
    every call, and nothing in the UI uses them — they are debugging tools that
    happened to sit on the same public path prefix as the product. With one ALB
    routing `/api/*` to the backend, that made them reachable by anyone who
    knew the URL.

    The global `API_KEY` gate cannot serve here: the SPA would have to carry
    that key in its bundle, where it is readable by everyone the gate is meant
    to exclude. So these use a separate key that only an operator holds.

    Unset, they are closed in production and open in development, which keeps
    the tooling usable locally without leaving a hole in a deployment that
    never configured it. 404 rather than 403 so the response says nothing
    about what is there.
    """
    settings = get_settings()
    if not settings.admin_api_key:
        if settings.is_production:
            raise HTTPException(status_code=404, detail="Not Found")
        return
    provided = request.headers.get("x-admin-key", "")
    if not hmac.compare_digest(provided.encode(), settings.admin_api_key.encode()):
        raise HTTPException(status_code=404, detail="Not Found")


def sanitize_user_text(text: str, max_length: int = 4000) -> str:
    """Bound and clean user-supplied text before it reaches prompts or APIs."""
    cleaned = text.replace("\x00", " ").strip()
    return cleaned[:max_length]
