"""Multi-source news search.

Fans out to every enabled publisher concurrently and merges the results. A
source that fails or is unconfigured is skipped rather than failing the whole
request.
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.guardian.models import GuardianSearchResult, NormalizedArticle
from app.sources import enabled_sources
from app.sources.base import NewsSourceError, SourceResult

logger = logging.getLogger(__name__)

# publishers cap paging anyway; keep the UI's range sane
MAX_PAGES = 50


def _dedupe(articles: list[NormalizedArticle]) -> list[NormalizedArticle]:
    merged: list[NormalizedArticle] = []
    seen: set[str] = set()
    for article in articles:
        key = article.url or article.article_id
        if key not in seen:
            seen.add(key)
            merged.append(article)
    return merged


def _published(article: NormalizedArticle) -> datetime:
    """Comparable timestamp: publishers differ on whether they send an offset,
    and mixing naive with aware datetimes raises on comparison."""
    dt = article.published_at
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def merge(
    groups: list[list[NormalizedArticle]], order_by: str = "newest"
) -> list[NormalizedArticle]:
    """Combine the sources into one list, deduped.

    Date orders sort across publishers, so the genuinely freshest article leads
    regardless of who published it. Relevance is the exception: publishers score
    on their own scales, so those scores can't be compared across sources — a
    round-robin is the only honest merge, and it keeps each source's ranking.
    """
    if order_by == "relevance":
        rows = max((len(g) for g in groups), default=0)
        ordered = [g[row] for row in range(rows) for g in groups if row < len(g)]
        return _dedupe(ordered)

    articles = _dedupe([a for group in groups for a in group])
    dated = [a for a in articles if a.published_at]
    undated = [a for a in articles if not a.published_at]
    dated.sort(key=_published, reverse=order_by != "oldest")
    # undated last either way: there is no date that legitimately outranks a real one
    return dated + undated


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

    # ask each source for a full page: when one publisher happens to own the
    # freshest N, a per-source share would truncate it out of the ranking.
    # Costs no extra requests — just a larger page on the same one.
    per_source = page_size or 12

    async def run(source) -> SourceResult:
        try:
            return await source.search_page(
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
            return SourceResult()

    results = await asyncio.gather(*(run(source) for source in active))
    merged = merge([r.articles for r in results], order_by)[: page_size or 12]

    # Publishers paginate independently: we can keep serving pages while any
    # of them still has more, so the deepest source sets the page count.
    pages = max([r.pages for r in results] + [1])
    return GuardianSearchResult(
        total=sum(r.total for r in results),
        page=page,
        pages=min(pages, MAX_PAGES),
        page_size=page_size or 12,
        articles=merged,
    )
