"""Scheduled Guardian ingestion job.

Fetches recent articles for the configured sections and indexes only unseen
or updated ones (never the whole archive). Run it periodically, e.g. via
host cron every 30 minutes:

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
from app.guardian.client import get_guardian_client
from app.rag.ingestion import ingest_articles

logger = logging.getLogger(__name__)

# us-news first: the app favours the Guardian's US desk, so keep that
# section warm in the index rather than relying on ranking alone
DEFAULT_SECTIONS = ["us-news", "technology", "business", "world", "politics", "environment"]


async def ingest_recent(sections: list[str] | None = None, days_back: int = 1) -> None:
    configure_logging(get_settings().log_level)
    await init_db()
    client = get_guardian_client()
    from_date = (date.today() - timedelta(days=days_back)).isoformat()

    sections = sections or DEFAULT_SECTIONS
    # fetch all sections concurrently; ingestion shares one session so it stays sequential
    results = await asyncio.gather(
        *(
            client.search(section=section, from_date=from_date, order_by="newest", page_size=20)
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
    await client.aclose()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(ingest_recent())
