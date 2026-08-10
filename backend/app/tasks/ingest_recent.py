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
from app.rag.ingestion import ingest_articles

logger = logging.getLogger(__name__)

# us-news first: the app favours the Guardian's US desk, so keep that
# section warm in the index rather than relying on ranking alone
DEFAULT_SECTIONS = ["us-news", "technology", "business", "world", "politics", "environment"]


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


async def ingest_recent(sections: list[str] | None = None, days_back: int = 1) -> None:
    from_date = (date.today() - timedelta(days=days_back)).isoformat()

    sections = sections or DEFAULT_SECTIONS
    # fetch all sections concurrently; ingestion shares one session so it stays sequential
    results = await asyncio.gather(
        *(
            search_news(section=section, from_date=from_date, order_by="newest", page_size=20)
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
