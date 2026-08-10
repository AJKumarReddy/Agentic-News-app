"""In-process ingestion scheduler.

Runs the multi-source ingestion on a fixed interval for as long as the API is
up, so the index stays current without an external cron.

Two details worth knowing:

* Under Gunicorn every worker runs this loop, so each tick is guarded by a
  short-lived Redis lock — exactly one worker performs the run and the others
  skip it. Without the lock, N workers would multiply the publishers' API
  usage by N and race on the same rows.
* A failed run never stops the loop; it is logged and retried on the next
  tick. Publisher APIs are flaky by nature and the index is a cache.
* A tick refreshes a slice of the sections rather than all of them, cycling
  through the list so a short interval stays under the publishers' daily
  request cap. See `rotating_sections`.
"""

import asyncio
import logging
import time
import uuid

from app.core.config import get_settings
from app.core.logging import Timer, log_event
from app.services.cache import get_redis
from app.tasks.ingest_recent import ingest_recent, rotating_sections

logger = logging.getLogger(__name__)

LOCK_KEY_PREFIX = "ingest:tick-lock"


async def _acquire_tick_lock(tick: int, ttl_seconds: int) -> bool:
    """True when this worker owns `tick`.

    Keyed per tick, not globally: a tick must never be blocked by the previous
    one's lease. The first tick after startup runs off-boundary, so under a
    single shared key its lease could still be live at the next boundary and
    silently drop that tick.

    Fails open: if Redis is unavailable we still ingest rather than letting a
    cache outage silently freeze the index.
    """
    try:
        redis = get_redis()
        key = f"{LOCK_KEY_PREFIX}:{tick}"
        acquired = await redis.set(key, uuid.uuid4().hex, nx=True, ex=ttl_seconds)
        return bool(acquired)
    except Exception:
        logger.warning("ingest lock unavailable; proceeding without it", exc_info=True)
        return True


async def run_scheduler() -> None:
    settings = get_settings()
    interval = max(1, settings.ingest_interval_minutes) * 60
    # let the API finish starting before the first pull
    await asyncio.sleep(settings.ingest_start_delay_seconds)

    while True:
        try:
            # derived from the clock, so every worker agrees on which tick this
            # is — both for the lock and for the slice it should refresh
            tick = int(time.time()) // interval
            # the lease only has to outlive the run itself; the key is unique
            # per tick, so it can never block the following one
            if await _acquire_tick_lock(tick, max(60, interval)):
                sections = rotating_sections(tick, settings.ingest_sections_per_tick)
                with Timer() as timer:
                    await ingest_recent(sections=sections)
                log_event(
                    logger,
                    "scheduled_ingest_tick",
                    sections=",".join(sections),
                    latency_ms=timer.ms,
                )
            else:
                log_event(logger, "scheduled_ingest_skipped", reason="another worker holds the tick")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("scheduled ingestion failed; will retry next tick")
        # sleep to the next interval boundary rather than a flat interval: a
        # fixed sleep drifts by each run's duration, and because the rotation
        # is keyed on the clock, drift would eventually skip sections
        await asyncio.sleep(interval - (time.time() % interval))


def start(app) -> asyncio.Task | None:
    """Start the loop unless it is disabled or no publisher is configured."""
    settings = get_settings()
    if not settings.ingest_enabled:
        logger.info("scheduled ingestion disabled")
        return None
    if not (settings.guardian_api_key or settings.nyt_api_key):
        logger.info("scheduled ingestion idle: no publisher API key configured")
        return None
    task = asyncio.create_task(run_scheduler(), name="scheduled-ingestion")
    log_event(
        logger,
        "scheduled_ingest_started",
        every_minutes=settings.ingest_interval_minutes,
        sections_per_tick=settings.ingest_sections_per_tick,
        first_run_in_seconds=settings.ingest_start_delay_seconds,
    )
    return task


async def stop(task: asyncio.Task | None) -> None:
    if task is None:
        return
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass
