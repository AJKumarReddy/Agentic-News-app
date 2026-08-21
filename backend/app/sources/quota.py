"""Daily request budget for metered sources, shared across workers.

TheNewsAPI's free plan allows 100 requests a day. Scheduled ingestion calls
`search_news`, which fans out to every enabled publisher, so at a five-minute
tick the background job alone would issue 288 requests — the budget would be
gone before lunch and every request a reader was actually waiting on would
fail. This module is what keeps those two uses from competing.

Two ideas, both small:

* **Who is asking.** `background_ingest` is set by the ingestion task and read
  by the adapter, so the same `search_page` call can spend from a different
  pool depending on why it is running. A ContextVar rather than a `background=`
  keyword because that keyword would have to be threaded through the abstract
  signature in `base.py` and every adapter implementing it, for the benefit of
  one source.

* **How much is left.** A counter in Redis keyed by UTC day, so all Gunicorn
  workers spend from one budget rather than one each.

The counter fails *open*: if Redis is unreachable we allow the call. Going over
the plan's limit returns a 402 from the publisher, which the adapter already
turns into a normal `NewsSourceError` and the search service already answers
from the stored articles. Failing closed would instead mute the source
completely every time the cache blinked, which is the worse trade.
"""

import logging
from contextvars import ContextVar
from datetime import datetime, timezone

from app.services.cache import get_redis

logger = logging.getLogger(__name__)

#: True while the scheduled ingestion job is driving the request.
background_ingest: ContextVar[bool] = ContextVar("background_ingest", default=False)

#: Kept two days so a counter written just before midnight cannot outlive its
#: usefulness, without needing an exact expiry at the day boundary.
_TTL_SECONDS = 172_800


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def spend(source_id: str, limit: int) -> bool:
    """Claim one request against today's budget for `source_id`.

    Returns False when the claim would exceed `limit`, in which case the caller
    must not make the request. A non-positive limit means "no budget at all"
    and is always refused — that is how the reserve turns background traffic
    off once it has eaten its share.
    """
    if limit <= 0:
        return False
    key = f"quota:{source_id}:{_today()}"
    try:
        redis = get_redis()
        used = await redis.incr(key)
        if used == 1:
            await redis.expire(key, _TTL_SECONDS)
    except Exception:
        logger.warning("quota counter unavailable for %s; allowing", source_id, exc_info=True)
        return True
    if used > limit:
        return False
    return True


async def spent_today(source_id: str) -> int:
    """How many requests today's budget has already been charged. Reporting
    only — never gate on this, since it races with `spend`."""
    try:
        raw = await get_redis().get(f"quota:{source_id}:{_today()}")
        return int(raw) if raw else 0
    except Exception:
        return 0
