"""Agent tools. Each tool is a plain async function with structured inputs
and outputs; the LangGraph graph calls them in a controlled order, and the
REST API exposes some of them directly."""

import asyncio
import logging
from dataclasses import asdict, replace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.guardian.models import NormalizedArticle
from app.sources import enabled_sources, source_for_article
from app.sources.base import NewsSourceError
from app.sources.registry import source_domains
from app.rag.ingestion import ingest_articles
from app.rag.reranker import rerank_chunks
from app.rag.retrieval import hybrid_retrieve
from app.rag.vector_store import RetrievalFilters, ScoredChunk
from app.services.search_service import search_news
from app.websearch.client import WebResult, get_web_client

logger = logging.getLogger(__name__)


async def search_web(
    query: str,
    max_results: int | None = None,
    days: int | None = None,
    news_like: bool = True,
    allow_domains: list[str] | None = None,
) -> list[WebResult]:
    """Web search (Tavily) with quality gates. Guardian domains are excluded so
    web results never duplicate or masquerade as Guardian reporting.
    Returns [] when no TAVILY_API_KEY is configured."""
    settings = get_settings()
    return await get_web_client().search(
        query,
        max_results=max_results or settings.web_search_max_results,
        topic="news" if news_like else "general",
        days=days,
        # never duplicate publishers we already cite directly
        exclude_domains=source_domains(),
        allow_domains=allow_domains,
    )


async def search_publishers(
    query: str,
    from_date: str | None = None,
    to_date: str | None = None,
    section: str | None = None,
    order_by: str = "newest",
) -> list[NormalizedArticle]:
    """Search every enabled publisher; empty list on failure."""
    try:
        result = await search_news(
            query=query, from_date=from_date, to_date=to_date, section=section, order_by=order_by
        )
        return result.articles
    except Exception as exc:  # noqa: BLE001 - a search failure must not end the turn
        logger.warning("search_publishers failed: %s", exc)
        return []


async def get_source_article(article_id: str) -> NormalizedArticle | None:
    """Retrieve one article from whichever publisher owns its id."""
    source = source_for_article(article_id)
    if source is None:
        return None
    try:
        return await source.get_article(article_id)
    except NewsSourceError:
        return None


async def index_guardian_articles(
    session: AsyncSession, articles: list[NormalizedArticle]
) -> dict[str, Any]:
    """Index new/updated articles into the vector store (incremental, deduplicated)."""
    return asdict(await ingest_articles(session, articles))


def ensure_source_diversity(
    selected: list[ScoredChunk], candidates: list[ScoredChunk], reserved: int = 1
) -> list[ScoredChunk]:
    """Give each publisher a foothold in the final evidence.

    Publishers expose very different amounts of text — the NYT API returns
    only abstracts, so its chunks are an order of magnitude shorter than
    full-text ones and lose on raw relevance almost every time. Without this,
    an answer would silently become single-source. Reserved slots replace the
    weakest chunks of the dominant source, so relevance still leads.
    """
    if not selected or not candidates:
        return selected

    present = {getattr(s.chunk, "source_id", "") for s in selected}
    missing = [
        c for c in candidates if getattr(c.chunk, "source_id", "") not in present
    ]
    if not missing:
        return selected

    result = list(selected)
    for source_id in dict.fromkeys(getattr(c.chunk, "source_id", "") for c in missing):
        best = next(c for c in missing if getattr(c.chunk, "source_id", "") == source_id)
        # drop the lowest-ranked chunk of the most represented source
        dominant = max(present, key=lambda s: sum(
            1 for c in result if getattr(c.chunk, "source_id", "") == s
        ))
        droppable = [i for i, c in enumerate(result) if getattr(c.chunk, "source_id", "") == dominant]
        if len(droppable) <= reserved:
            break
        result[droppable[-1]] = best
        present.add(source_id)
    return result


async def retrieve_rag(
    session: AsyncSession,
    query: str,
    filters: RetrievalFilters | None = None,
    top_k: int | None = None,
    freshness: bool = False,
    rerank: bool = True,
    diversify: bool = True,
) -> list[ScoredChunk]:
    """Hybrid retrieval over indexed chunks from all publishers, reranked."""
    settings = get_settings()
    pool = top_k or settings.rag_initial_top_k
    source_ids = [s.id for s in enabled_sources()]

    if diversify and len(source_ids) > 1 and not (filters and filters.source_ids):
        # Retrieve per publisher, then rank together. A shared pool is unfair
        # across sources with very different text lengths: NYT returns only
        # abstracts, so its chunks never reached the candidate list at all.
        per_source = max(4, pool // len(source_ids))
        groups = []
        for source_id in source_ids:
            scoped = replace(filters or RetrievalFilters(), source_ids=[source_id])
            groups.append(
                await hybrid_retrieve(
                    session, query, filters=scoped, top_k=per_source, freshness=freshness
                )
            )
        candidates = [chunk for group in groups for chunk in group]
        candidates.sort(key=lambda s: s.score, reverse=True)
    else:
        candidates = await hybrid_retrieve(
            session, query, filters=filters, top_k=pool, freshness=freshness
        )
    if rerank and candidates:
        selected = await rerank_chunks(query, candidates, settings.rag_final_top_k)
    else:
        selected = candidates[: settings.rag_final_top_k]
    return ensure_source_diversity(selected, candidates) if diversify else selected


async def fetch_and_index(
    session: AsyncSession,
    queries: list[str],
    article_ids: list[str] | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    section: str | None = None,
    order_by: str = "newest",
) -> dict[str, Any]:
    """Fetch by search queries and/or explicit IDs concurrently, then index
    everything found. This is the freshness path: Guardian API first, RAG second."""
    searches = [
        search_publishers(q, from_date=from_date, to_date=to_date, section=section, order_by=order_by)
        for q in queries[:3]
    ]
    lookups = [get_source_article(article_id) for article_id in (article_ids or [])[:25]]
    results = await asyncio.gather(*searches, *lookups)

    seen: dict[str, NormalizedArticle] = {}
    for result in results:
        for article in result if isinstance(result, list) else ([result] if result else []):
            seen.setdefault(article.article_id, article)

    stats = asdict(await ingest_articles(session, list(seen.values())))
    stats["found"] = len(seen)
    stats["article_ids"] = list(seen.keys())
    return stats


async def compare_articles(
    session: AsyncSession,
    subjects: list[str],
    filters: RetrievalFilters | None = None,
) -> dict[str, list[ScoredChunk]]:
    """Gather evidence per subject for comparison answers.

    Takes the caller's filters whole. Rebuilding them here from a pair of date
    strings silently dropped every other constraint the user set — a section
    filter never reached a comparison.
    """
    evidence: dict[str, list[ScoredChunk]] = {}
    per_subject = max(3, get_settings().rag_final_top_k // max(1, len(subjects)))
    for subject in subjects[:4]:
        chunks = await retrieve_rag(session, subject, filters=filters, freshness=True, rerank=True)
        evidence[subject] = chunks[:per_subject]
    return evidence


async def build_timeline(
    session: AsyncSession,
    topic: str,
    filters: RetrievalFilters | None = None,
) -> list[ScoredChunk]:
    """Retrieve related chunks and order them chronologically."""
    chunks = await retrieve_rag(session, topic, filters=filters, freshness=False, rerank=True)
    return sorted(
        chunks,
        key=lambda s: (s.chunk.published_at.timestamp() if s.chunk.published_at else 0),
    )
