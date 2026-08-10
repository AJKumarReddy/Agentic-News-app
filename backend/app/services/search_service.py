"""Multi-source news search.

Fans out to every enabled publisher concurrently and interleaves the results
so no single source dominates the first page. A source that fails or is
unconfigured is skipped rather than failing the whole request.
"""

import asyncio
import logging

from app.guardian.models import GuardianSearchResult, NormalizedArticle
from app.sources import enabled_sources
from app.sources.base import NewsSourceError

logger = logging.getLogger(__name__)


def interleave(groups: list[list[NormalizedArticle]]) -> list[NormalizedArticle]:
    """Round-robin merge, preserving each source's own ranking."""
    merged: list[NormalizedArticle] = []
    seen: set[str] = set()
    for row in range(max((len(g) for g in groups), default=0)):
        for group in groups:
            if row < len(group):
                article = group[row]
                key = article.url or article.article_id
                if key not in seen:
                    seen.add(key)
                    merged.append(article)
    return merged


async def search_news(
    query: str = "",
    from_date: str | None = None,
    to_date: str | None = None,
    section: str | None = None,
    tag: str | None = None,
    author: str | None = None,
    order_by: str = "newest",
    page: int = 1,
    page_size: int | None = None,
    sources: list[str] | None = None,
) -> GuardianSearchResult:
    active = [s for s in enabled_sources() if not sources or s.id in sources]
    if not active:
        return GuardianSearchResult(total=0, page=page, pages=1, page_size=page_size or 12)

    per_source = max(4, (page_size or 12) // max(1, len(active)) + 2)

    async def run(source):
        try:
            return await source.search(
                query=query,
                from_date=from_date,
                to_date=to_date,
                section=section,
                order_by=order_by,
                page=page,
                page_size=per_source,
            )
        except NewsSourceError as exc:
            logger.warning("source %s failed: %s", source.id, exc)
            return []

    groups = await asyncio.gather(*(run(source) for source in active))
    merged = interleave(list(groups))[: page_size or 12]

    return GuardianSearchResult(
        total=sum(len(g) for g in groups),
        page=page,
        # every source paginates differently; expose a usable page count
        pages=max(1, page + (1 if any(len(g) >= per_source for g in groups) else 0)),
        page_size=page_size or 12,
        articles=merged,
    )
