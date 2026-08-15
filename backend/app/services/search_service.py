"""Multi-source news search.

Fans out to every enabled publisher concurrently and merges the results. A
source that fails or is unconfigured falls back to what we already stored for
it rather than silently vanishing from the page: publisher developer keys are
rate limited, and an unreachable publisher is a routine event here, not an
exception. Every live result is written back to that store, so the fallback is
kept warm by ordinary browsing at no extra cost in publisher quota.
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.guardian.models import GuardianSearchResult, NormalizedArticle
from app.sources import enabled_sources
from app.sources.base import NewsSource, NewsSourceError, SourceResult

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


def _as_datetime(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if end_of_day:
        parsed = parsed.replace(hour=23, minute=59, second=59)
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


async def _remember(articles: list[NormalizedArticle]) -> None:
    """Persist live results so an unreachable publisher still has a page to show.

    Article rows only — no embeddings. Chunking every browse would put an LLM
    call on the request path; the vector index is filled by ingestion, while
    this only has to answer "what did we last see from this publisher".
    """
    if not articles:
        return
    from app.database.repositories import ArticleRepository
    from app.database.session import SessionFactory

    try:
        async with SessionFactory() as session:
            repo = ArticleRepository(session)
            for article in articles:
                await repo.upsert(article)
            await session.commit()
    except Exception:  # noqa: BLE001 - a warm cache is never worth failing a search
        logger.warning("could not persist search results", exc_info=True)


async def _from_store(
    source: NewsSource,
    *,
    query: str,
    section: str | None,
    from_date: str | None,
    to_date: str | None,
    order_by: str,
    page: int,
    page_size: int,
) -> SourceResult:
    """What we already hold for a publisher we could not reach."""
    from app.database.repositories import ArticleRepository, to_normalized
    from app.database.session import SessionFactory

    try:
        async with SessionFactory() as session:
            rows, total = await ArticleRepository(session).search_stored(
                source_id=source.id,
                query=query,
                section=section,
                from_date=_as_datetime(from_date),
                to_date=_as_datetime(to_date, end_of_day=True),
                order_by=order_by,
                page=page,
                page_size=page_size,
            )
    except Exception:  # noqa: BLE001 - degrade to empty, never to a 500
        logger.warning("stored fallback failed for %s", source.id, exc_info=True)
        return SourceResult()

    if not rows:
        return SourceResult()
    logger.info("serving %s from store: %d of %d", source.id, len(rows), total)
    pages = max(1, -(-total // page_size))  # ceil
    return SourceResult(
        articles=[to_normalized(row) for row in rows], total=total, pages=pages
    )


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

    async def run(source) -> tuple[SourceResult, bool]:
        try:
            result = await source.search_page(
                query=query,
                from_date=from_date,
                to_date=to_date,
                section=section,
                order_by=order_by,
                page=page,
                page_size=per_source,
            )
            return result, True
        except NewsSourceError as exc:
            logger.warning("source %s failed: %s", source.id, exc)
            return SourceResult(), False

    outcomes = await asyncio.gather(*(run(source) for source in active))

    # keep the store warm from traffic we already paid for
    await _remember([a for result, live in outcomes if live for a in result.articles])

    degraded: list[str] = []
    results: list[SourceResult] = []
    for source, (result, live) in zip(active, outcomes):
        if live:
            results.append(result)
            continue
        stored = await _from_store(
            source,
            query=query,
            section=section,
            from_date=from_date,
            to_date=to_date,
            order_by=order_by,
            page=page,
            page_size=per_source,
        )
        results.append(stored)
        if stored.articles:
            degraded.append(source.id)

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
        degraded_sources=degraded,
    )
