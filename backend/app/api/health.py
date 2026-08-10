import asyncio

from fastapi import APIRouter

from app.database.session import check_db, check_vector_extension
from app.guardian.client import get_guardian_client
from app.services.cache import cache_get, cache_set, check_redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    # independent probes run concurrently; this endpoint is polled frequently
    database_ok, vector_ok, redis_ok, guardian_status = await asyncio.gather(
        check_db(), check_vector_extension(), check_redis(), cache_get("health:guardian")
    )

    # Guardian availability is cached for 60s to avoid hammering the API
    if guardian_status is None:
        guardian_status = "available" if await get_guardian_client().ping() else "unavailable"
        await cache_set("health:guardian", guardian_status, ttl=60)

    healthy = database_ok and vector_ok
    return {
        "status": "healthy" if healthy else "degraded",
        "database": "connected" if database_ok else "disconnected",
        "vector_database": "connected" if vector_ok else "disconnected",
        "cache": "connected" if redis_ok else "disconnected",
        "guardian_api": guardian_status,
    }
