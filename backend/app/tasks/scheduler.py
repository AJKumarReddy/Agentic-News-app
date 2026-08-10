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
"""

import asyncio
import logging
import uuid

from app.core.config import get_settings
from app.core.logging import Timer, log_event
from app.services.cache import get_redis
from app.tasks.ingest_recent import ingest_recent

logger = logging.getLogger(__name__)

LOCK_KEY = "ingest:tick-lock"


async def _acquire_tick_lock(ttl_seconds: int) -> bool:
    """True when this worker owns the current tick.

    Fails open: if Redis is unavailable we still ingest rather than letting a
    cache outage silently freeze the index.
    """
    try:
        redis = get_redis()
        acquired = await redis.set(LOCK_KEY, uuid.uuid4().hex, nx=True, ex=ttl_seconds)
        return bool(acquired)
    except Exception:
        logger.warning("ingest lock unavailable; proceeding without it", exc_info=True)
        return True


async def run_scheduler() -> None:
    settings = get_settings()
    interval = max(5, settings.ingest_interval_minutes) * 60
    # let the API finish starting before the first pull
    await asyncio.sleep(settings.ingest_start_delay_seconds)

    while True:
        try:
            # lock expires just before the next tick, so a crashed worker
            # doesn't block the following run
            if await _acquire_tick_lock(interval - 30):
                with Timer() as timer:
                    await ingest_recent()
                log_event(logger, "scheduled_ingest_tick", latency_ms=timer.ms)
            else:
                log_event(logger, "scheduled_ingest_skipped", reason="another worker holds the tick")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("scheduled ingestion failed; will retry next tick")
        await asyncio.sleep(interval)


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
