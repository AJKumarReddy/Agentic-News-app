"""Security middleware: secure headers + a lightweight per-IP rate limiter.

The rate limiter is an in-process sliding window, sufficient for a single
EC2 instance behind nginx. For a multi-instance deployment, swap the storage
for Redis (the interface is contained in RateLimiter).
"""

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
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for key, value in _SECURE_HEADERS.items():
            response.headers.setdefault(key, value)
        return response


class RateLimiter:
    def __init__(self, limit_per_minute: int):
        self.limit = limit_per_minute
        self.window = 60.0
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    EXEMPT_PATHS = {"/api/health"}

    def __init__(self, app, limit_per_minute: int = 30):
        super().__init__(app)
        self.limiter = RateLimiter(limit_per_minute)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in self.EXEMPT_PATHS or request.method == "OPTIONS":
            return await call_next(request)
        # nginx sets X-Forwarded-For; fall back to the socket address
        forwarded = request.headers.get("x-forwarded-for", "")
        client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
        if not self.limiter.allow(client_ip):
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please slow down."},
                headers={"Retry-After": "30"},
            )
        return await call_next(request)


def sanitize_user_text(text: str, max_length: int = 4000) -> str:
    """Bound and clean user-supplied text before it reaches prompts or APIs."""
    cleaned = text.replace("\x00", " ").strip()
    return cleaned[:max_length]
