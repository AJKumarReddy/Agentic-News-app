import asyncio

import pytest

import app.tasks.scheduler as scheduler_module
from app.tasks.scheduler import _acquire_tick_lock, start, stop


class FakeRedis:
    """Mimics SET NX EX: only the first caller in a window wins."""

    def __init__(self):
        self.keys = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.keys:
            return None
        self.keys[key] = value
        return True


async def test_only_one_worker_wins_a_tick(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(scheduler_module, "get_redis", lambda: redis)
    results = [await _acquire_tick_lock(60) for _ in range(3)]
    # duplicate runs would multiply publisher API usage by the worker count
    assert results == [True, False, False]


async def test_lock_failure_still_ingests(monkeypatch):
    def boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr(scheduler_module, "get_redis", boom)
    # a cache outage must not silently freeze the index
    assert await _acquire_tick_lock(60) is True


def test_disabled_scheduler_starts_nothing(monkeypatch):
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("INGEST_ENABLED", "false")
    assert start(None) is None
    get_settings.cache_clear()


def test_no_publisher_key_starts_nothing(monkeypatch):
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("INGEST_ENABLED", "true")
    monkeypatch.setenv("GUARDIAN_API_KEY", "")
    monkeypatch.setenv("NYT_API_KEY", "")
    assert start(None) is None
    get_settings.cache_clear()


async def test_stop_cancels_a_running_loop():
    async def forever():
        await asyncio.sleep(3600)

    task = asyncio.create_task(forever())
    await stop(task)
    assert task.cancelled() or task.done()


async def test_stop_tolerates_no_task():
    await stop(None)
