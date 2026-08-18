import asyncio

from fastapi import APIRouter

from app.database.session import check_db, check_vector_extension
from app.services.cache import cache_get, cache_set, check_redis
from app.services.stt_service import transcription_enabled
from app.services.tts_service import speech_enabled
from app.sources import enabled_sources

router = APIRouter(tags=["health"])


@router.get("/capabilities")
async def capabilities():
    """What this deployment can actually do, for the UI to shape itself around.

    Kept out of /api/health, which is a monitoring surface the SPA never calls.
    A control the backend cannot serve should not be rendered at all.
    """
    return {"tts": speech_enabled(), "stt": transcription_enabled()}


@router.get("/health")
async def health():
    # independent probes run concurrently; this endpoint is polled frequently
    database_ok, vector_ok, redis_ok, cached_sources = await asyncio.gather(
        check_db(), check_vector_extension(), check_redis(), cache_get("health:sources")
    )

    # publisher availability is cached for 60s to stay inside their rate limits
    if cached_sources is None:
        results = await asyncio.gather(
            *(source.ping() for source in enabled_sources()), return_exceptions=True
        )
        cached_sources = {
            source.id: ("available" if result is True else "unavailable")
            for source, result in zip(enabled_sources(), results)
        }
        await cache_set("health:sources", cached_sources, ttl=60)

    healthy = database_ok and vector_ok
    return {
        "status": "healthy" if healthy else "degraded",
        "database": "connected" if database_ok else "disconnected",
        "vector_database": "connected" if vector_ok else "disconnected",
        "cache": "connected" if redis_ok else "disconnected",
        "sources": cached_sources,
    }
