"""Daily request budget per publisher, shared across workers.

Every publisher meters separately and at a different size — the Guardian and
the NYT allow 500 requests a day on a developer key, TheNewsAPI 2,500 on its
Basic plan — so the caps here are per source, and so are the counters. One
shared ceiling would have to be the smallest of them, which would throttle a
generous plan to a mean one and still overspend the other way round if a plan
changed.

Scheduled ingestion calls `search_news`, which fans out to every enabled
publisher, so the sweep alone issues a few hundred requests a day against each
of them. This module is what keeps that from competing with the requests a
reader is waiting on: the reserve matters at any plan size, because it is what
stops a shortened interval or a wider sweep from eating them.

Two ideas, both small:

* **Who is asking.** `background_ingest` is set by the ingestion task and read
  by the adapter, so the same `search_page` call can spend from a different
  pool depending on why it is running. A ContextVar rather than a `background=`
  keyword because that keyword would have to be threaded through the abstract
  signature in `base.py` and every adapter implementing it, for the benefit of
  one source.

* **How much is left.** A counter in Redis keyed by source and UTC day, so all
  Gunicorn workers spend from one budget per publisher rather than one each.

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


async def claim(source_id: str, daily_budget: int, interactive_reserve: int) -> bool:
    """Claim one request against `source_id`'s own budget for today.

    The publisher's plan decides `daily_budget`; a budget of 0 means this
    source is not metered here at all and the call always proceeds. That is the
    default, so adding an adapter costs nothing until someone knows what its
    plan actually allows — a made-up ceiling would throttle a publisher for no
    reason, which is worse than not counting.

    Ingestion runs unattended and can afford to miss a tick; somebody waiting
    on a search cannot. So background work is held to `daily_budget -
    interactive_reserve` and stops while there is still quota for the
    interactive path. A reserve at or above the budget leaves background work
    nothing, which is how it is turned off outright.
    """
    if daily_budget <= 0:
        return True
    limit = daily_budget
    if background_ingest.get():
        limit -= interactive_reserve
    return await spend(source_id, limit)


async def spent_today(source_id: str) -> int:
    """How many requests today's budget has already been charged. Reporting
    only — never gate on this, since it races with `spend`."""
    try:
        raw = await get_redis().get(f"quota:{source_id}:{_today()}")
        return int(raw) if raw else 0
    except Exception:
        return 0
