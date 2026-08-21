import asyncio

import pytest

import app.tasks.scheduler as scheduler_module
from app.tasks.ingest_recent import DEFAULT_SECTIONS, rotating_sections
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
    results = [await _acquire_tick_lock(7, 60) for _ in range(3)]
    # duplicate runs would multiply publisher API usage by the worker count
    assert results == [True, False, False]


async def test_a_tick_is_never_blocked_by_the_previous_lease(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(scheduler_module, "get_redis", lambda: redis)
    # the first tick after startup runs off-boundary, so its lease can still
    # be live when the next boundary arrives; that must not drop the tick
    assert await _acquire_tick_lock(7, 3600) is True
    assert await _acquire_tick_lock(8, 3600) is True


async def test_lock_failure_still_ingests(monkeypatch):
    def boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr(scheduler_module, "get_redis", boom)
    # a cache outage must not silently freeze the index
    assert await _acquire_tick_lock(7, 60) is True


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
    # every publisher has to be silenced, not just the two this test was
    # written against — one configured key is enough to justify the loop
    monkeypatch.setenv("THENEWSAPI_API_KEY", "")
    assert start(None) is None
    get_settings.cache_clear()


def test_rotation_covers_every_section_without_repeating():
    n = len(DEFAULT_SECTIONS)
    picked = [rotating_sections(tick)[0] for tick in range(n)]
    # a section starved of ticks would silently go stale in the index
    assert sorted(picked) == sorted(DEFAULT_SECTIONS)


def test_rotation_is_a_pure_function_of_the_tick():
    # workers derive the slice independently; disagreement would double-fetch
    assert rotating_sections(7) == rotating_sections(7)
    assert rotating_sections(7) == rotating_sections(7 + len(DEFAULT_SECTIONS))


def test_rotation_slice_is_clamped_to_the_budget():
    n = len(DEFAULT_SECTIONS)
    for count in range(0, n + 2):
        sections = rotating_sections(3, count)
        # over-requesting blows the 500/day cap; a zero would freeze the index
        assert len(sections) == max(1, min(count, n))
        assert len(set(sections)) == len(sections)
        assert set(sections) <= set(DEFAULT_SECTIONS)


async def test_stop_cancels_a_running_loop():
    async def forever():
        await asyncio.sleep(3600)

    task = asyncio.create_task(forever())
    await stop(task)
    assert task.cancelled() or task.done()


async def test_stop_tolerates_no_task():
    await stop(None)
