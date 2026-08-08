"""Thin Redis cache wrapper. Degrades gracefully to no-op when Redis is
unavailable so a cache outage never takes the app down."""

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None
_available = True


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            get_settings().redis_url, decode_responses=True, socket_connect_timeout=5, socket_timeout=5
        )
    return _redis


async def cache_get(key: str) -> Any | None:
    global _available
    if not _available:
        return None
    try:
        raw = await get_redis().get(key)
        return json.loads(raw) if raw else None
    except Exception:
        _available = False
        logger.warning("Redis unavailable; caching disabled for this process")
        return None


async def cache_set(key: str, value: Any, ttl: int | None = None) -> None:
    global _available
    if not _available:
        return
    try:
        await get_redis().set(
            key, json.dumps(value, default=str), ex=ttl or get_settings().cache_ttl_seconds
        )
    except Exception:
        _available = False


async def check_redis() -> bool:
    try:
        return bool(await get_redis().ping())
    except Exception:
        return False
