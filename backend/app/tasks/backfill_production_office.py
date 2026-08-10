"""Backfill Guardian production_office on articles indexed before that field
was stored.

Metadata only — chunks and embeddings are untouched, so this costs Guardian
API calls but no embedding spend.

    python -m app.tasks.backfill_production_office
"""

import asyncio
import logging

from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.logging import configure_logging, log_event
from app.database.models import Article, Chunk
from app.database.session import SessionFactory, engine, init_db
from app.guardian.client import GuardianAPIError, get_guardian_client

logger = logging.getLogger(__name__)

CONCURRENCY = 8


async def backfill(limit: int = 1000) -> None:
    configure_logging(get_settings().log_level)
    await init_db()
    client = get_guardian_client()
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def fetch_office(article_id: str) -> tuple[str, str]:
        async with semaphore:
            try:
                article = await client.get_article(article_id)
                return article_id, article.production_office
            except GuardianAPIError:
                return article_id, ""

    async with SessionFactory() as session:
        result = await session.execute(
            select(Article.article_id)
            .where(Article.production_office == "", Article.source_id == "guardian")
            .limit(limit)
        )
        article_ids = [row[0] for row in result.all()]
        if not article_ids:
            log_event(logger, "backfill_complete", updated=0, reason="nothing to do")
            await client.aclose()
            await engine.dispose()
            return

        offices = await asyncio.gather(*(fetch_office(a) for a in article_ids))

        updated = 0
        for article_id, office in offices:
            if not office:
                continue
            await session.execute(
                update(Article).where(Article.article_id == article_id).values(production_office=office)
            )
            await session.execute(
                update(Chunk).where(Chunk.article_id == article_id).values(production_office=office)
            )
            updated += 1
        await session.commit()
        log_event(logger, "backfill_complete", checked=len(article_ids), updated=updated)

    await client.aclose()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(backfill())
