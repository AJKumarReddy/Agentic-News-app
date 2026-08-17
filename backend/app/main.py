import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import chat, health, news, rag
from app.core.config import get_settings
from app.core.logging import Timer, configure_logging, log_event, new_request_id
from app.core.security import (
    ApiKeyMiddleware,
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    TimeoutMiddleware,
)
from app.database.session import engine, init_db
from app.sources.base import NewsSourceError
from app.sources.registry import close_all
from app.tasks import scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    await init_db()
    ingestion_task = scheduler.start(app)
    logger.info("News AI backend started (%s)", settings.environment)
    yield
    await scheduler.stop(ingestion_task)
    await close_all()
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="News AI",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    # Starlette inserts each new middleware at the front of the stack, so the
    # LAST one added is the OUTERMOST. Registration order below is therefore
    # innermost → outermost, and the resulting stack matches the docstring in
    # app.core.security.
    app.add_middleware(TimeoutMiddleware, timeout_seconds=settings.request_timeout_seconds)
    app.add_middleware(
        RateLimitMiddleware,
        limit_per_minute=settings.rate_limit_per_minute,
        chat_limit_per_minute=settings.chat_rate_limit_per_minute,
    )
    app.add_middleware(ApiKeyMiddleware, api_key=settings.api_key)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_body_bytes)
    app.add_middleware(SecurityHeadersMiddleware)
    # CORS outermost, so responses the middlewares below short-circuit — 401,
    # 413, 429, 504 — still carry the CORS headers. Registered first, it ended
    # up innermost and never saw them: a cross-origin caller got an opaque
    # browser CORS failure instead of the status that was actually returned.
    # Explicit origins only, never "*".
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-Client-Id", "X-Admin-Key"],
    )
    if settings.allowed_hosts_list:
        from starlette.middleware.trustedhost import TrustedHostMiddleware

        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)

    @app.middleware("http")
    async def request_logging(request: Request, call_next):
        request_id = new_request_id()
        with Timer() as timer:
            response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        log_event(
            logger,
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            total_latency=timer.ms,
        )
        return response

    @app.exception_handler(NewsSourceError)
    async def news_source_error_handler(request: Request, exc: NewsSourceError):
        if exc.status_code == 404:
            return JSONResponse(status_code=404, content={"detail": "Article not found"})
        return JSONResponse(status_code=502, content={"detail": f"News source error: {exc}"})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s", request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    app.include_router(health.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(news.router, prefix="/api")
    app.include_router(rag.router, prefix="/api")
    return app


app = create_app()
