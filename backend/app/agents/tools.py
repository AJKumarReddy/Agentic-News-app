"""Agent tools. Each tool is a plain async function with structured inputs
and outputs; the LangGraph graph calls them in a controlled order, and the
REST API exposes some of them directly."""

import asyncio
import logging
from dataclasses import asdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.guardian.client import GuardianAPIError, get_guardian_client
from app.guardian.models import NormalizedArticle
from app.rag.ingestion import ingest_articles
from app.rag.reranker import rerank_chunks
from app.rag.retrieval import hybrid_retrieve
from app.rag.vector_store import RetrievalFilters, ScoredChunk
from app.services.search_service import search_news

logger = logging.getLogger(__name__)


async def search_guardian(
    query: str,
    from_date: str | None = None,
    to_date: str | None = None,
    section: str | None = None,
    order_by: str = "newest",
) -> list[NormalizedArticle]:
    """Search the Guardian via the cached search service; empty list on failure."""
    try:
        result = await search_news(
            query=query, from_date=from_date, to_date=to_date, section=section, order_by=order_by
        )
        return result.articles
    except GuardianAPIError as exc:
        logger.warning("search_guardian failed: %s", exc)
        return []


async def get_guardian_article(article_id: str) -> NormalizedArticle | None:
    """Retrieve a single Guardian article by its content ID."""
    try:
        return await get_guardian_client().get_article(article_id)
    except GuardianAPIError:
        return None


async def index_guardian_articles(
    session: AsyncSession, articles: list[NormalizedArticle]
) -> dict[str, Any]:
    """Index new/updated articles into the vector store (incremental, deduplicated)."""
    return asdict(await ingest_articles(session, articles))


async def retrieve_rag(
    session: AsyncSession,
    query: str,
    filters: RetrievalFilters | None = None,
    top_k: int | None = None,
    freshness: bool = False,
    rerank: bool = True,
) -> list[ScoredChunk]:
    """Hybrid retrieval over indexed Guardian chunks, optionally reranked."""
    settings = get_settings()
    candidates = await hybrid_retrieve(
        session, query, filters=filters, top_k=top_k or settings.rag_initial_top_k, freshness=freshness
    )
    if rerank and candidates:
        return await rerank_chunks(query, candidates, settings.rag_final_top_k)
    return candidates[: settings.rag_final_top_k]


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
        search_guardian(q, from_date=from_date, to_date=to_date, section=section, order_by=order_by)
        for q in queries[:3]
    ]
    lookups = [get_guardian_article(article_id) for article_id in (article_ids or [])[:25]]
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
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict[str, list[ScoredChunk]]:
    """Gather evidence per subject for comparison answers."""
    filters = RetrievalFilters.from_iso(from_date, to_date)
    evidence: dict[str, list[ScoredChunk]] = {}
    per_subject = max(3, get_settings().rag_final_top_k // max(1, len(subjects)))
    for subject in subjects[:4]:
        chunks = await retrieve_rag(session, subject, filters=filters, freshness=True, rerank=True)
        evidence[subject] = chunks[:per_subject]
    return evidence


async def build_timeline(
    session: AsyncSession,
    topic: str,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[ScoredChunk]:
    """Retrieve related chunks and order them chronologically."""
    filters = RetrievalFilters.from_iso(from_date, to_date)
    chunks = await retrieve_rag(session, topic, filters=filters, freshness=False, rerank=True)
    return sorted(
        chunks,
        key=lambda s: (s.chunk.published_at.timestamp() if s.chunk.published_at else 0),
    )
