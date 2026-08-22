"""Scheduled multi-source ingestion job.

Fetches recent articles from every enabled publisher for the configured sections and indexes only unseen
or updated ones (never the whole archive). Invoked directly it sweeps every
section, which suits a cold index or an external scheduler on a slower
interval; the in-process scheduler instead passes a rotating slice each tick
to stay under the publishers' daily request cap.

    docker compose exec backend python -m app.tasks.ingest_recent

The synchronous-in-a-process design keeps the initial deployment simple;
the same function can be dropped into Celery/APScheduler later.
"""

import asyncio
import logging
from datetime import date, timedelta

from app.core.config import get_settings
from app.core.logging import configure_logging, log_event
from app.database.session import SessionFactory, engine, init_db
from app.services.search_service import search_news
from app.sources import enabled_sources
from app.sources.categories import ingest_sections
from app.sources.quota import background_ingest
from app.rag.ingestion import ingest_articles

logger = logging.getLogger(__name__)

# Derived from the canonical categories rather than listed by hand. The old
# list was eleven Guardian slugs, which indexed `business` and `money` as two
# separate sweeps of one subject and spent a tick each cycle on
# `commentisfree` — opinion, not reporting. One slug per category means the
# rotation completes in under half the time, so everything in the index is
# fresher, and the indexer covers exactly what the feed prioritises.
#
# Breadth still matters within a category: retrieval widens a slug into its
# subject neighbours (see app/sources/sections.py), so indexing `politics`
# still answers questions filed under us-news and world.
DEFAULT_SECTIONS = ingest_sections()

#: Articles pulled per section per publisher per tick. A section can easily
#: publish more than a dozen pieces in the window between two ticks, and
#: anything past the cap is simply never indexed.
INGEST_PAGE_SIZE = 50

#: How far back a scheduled run looks. One day left gaps whenever the app was
#: stopped overnight — and those gaps are permanent, since a later run only
#: ever looks at its own window.
INGEST_DAYS_BACK = 3


def rotating_sections(tick: int, count: int = 1) -> list[str]:
    """The slice of sections a given tick should refresh.

    Every section costs one request per enabled publisher, and developer keys
    cap at 500 requests/day — so a short interval can only stay in budget by
    refreshing part of the list each tick and cycling through the rest. The
    slice is derived from `tick` rather than from in-process state so that
    every Gunicorn worker agrees on it and a restart doesn't reset the cycle.
    """
    n = len(DEFAULT_SECTIONS)
    count = max(1, min(count, n))
    start = (tick * count) % n
    return [DEFAULT_SECTIONS[(start + i) % n] for i in range(count)]


async def ingest_recent(
    sections: list[str] | None = None, days_back: int = INGEST_DAYS_BACK
) -> None:
    from_date = (date.today() - timedelta(days=days_back)).isoformat()

    sections = sections or DEFAULT_SECTIONS
    # Marks everything below as background work. A metered source reads this to
    # spend from its ingestion budget rather than the slice reserved for people
    # waiting on a search — see app.sources.quota. Set on this task's context,
    # so it does not leak into requests being served concurrently.
    background_ingest.set(True)

    # Only sources that return volume per request. An aggregator capped at
    # three articles a call would spend a metered budget here to add almost
    # nothing to the index, and every one of those requests is denied to a
    # reader waiting on a search. It still appears in search results — it is
    # excluded from the *sweep*, not from the product.
    bulk = [s.id for s in enabled_sources() if s.bulk_efficient]
    if not bulk:
        log_event(logger, "scheduled_ingest_skipped", reason="no bulk-efficient source")
        return

    # fetch all sections concurrently; ingestion shares one session so it stays sequential
    results = await asyncio.gather(
        *(
            search_news(
                section=section,
                from_date=from_date,
                order_by="newest",
                page_size=INGEST_PAGE_SIZE,
                sources=bulk,
            )
            for section in sections
        )
    )

    total_indexed = 0
    async with SessionFactory() as session:
        for section, result in zip(sections, results):
            stats = await ingest_articles(session, result.articles)
            total_indexed += stats.indexed + stats.updated
            log_event(
                logger,
                "scheduled_ingest_section",
                section=section,
                found=len(result.articles),
                articles_indexed=stats.indexed,
                skipped=stats.skipped,
            )
    log_event(logger, "scheduled_ingest_complete", articles_indexed=total_indexed)


async def _main() -> None:
    """Standalone entrypoint: owns the setup the API's lifespan does in-process."""
    configure_logging(get_settings().log_level)
    await init_db()
    try:
        await ingest_recent()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
