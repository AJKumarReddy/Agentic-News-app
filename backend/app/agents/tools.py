"""Agent tools. Each tool is a plain async function with structured inputs
and outputs; the LangGraph graph calls them in a controlled order, and the
REST API exposes some of them directly."""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.guardian.client import GuardianAPIError, get_guardian_client
from app.guardian.models import NormalizedArticle
from app.rag.ingestion import ingest_articles
from app.rag.reranker import rerank_chunks
from app.rag.retrieval import hybrid_retrieve
from app.rag.vector_store import RetrievalFilters, ScoredChunk

logger = logging.getLogger(__name__)


async def search_guardian(
    query: str,
    from_date: str | None = None,
    to_date: str | None = None,
    section: str | None = None,
    order_by: str = "newest",
    page: int = 1,
    page_size: int | None = None,
) -> list[NormalizedArticle]:
    """Search the Guardian Content API directly."""
    client = get_guardian_client()
    try:
        result = await client.search(
            query=query,
            from_date=from_date,
            to_date=to_date,
            section=section,
            order_by=order_by,
            page=page,
            page_size=page_size,
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
    stats = await ingest_articles(session, articles)
    return {
        "checked": stats.checked,
        "indexed": stats.indexed,
        "updated": stats.updated,
        "skipped": stats.skipped,
        "chunks_created": stats.chunks_created,
    }


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
    from_date: str | None = None,
    to_date: str | None = None,
    section: str | None = None,
    order_by: str = "newest",
) -> dict[str, Any]:
    """search_guardian for each query, then index everything found.
    This is the freshness path: Guardian API first, RAG second."""
    seen: dict[str, NormalizedArticle] = {}
    for query in queries[:3]:
        articles = await search_guardian(
            query, from_date=from_date, to_date=to_date, section=section, order_by=order_by
        )
        for article in articles:
            seen.setdefault(article.article_id, article)
    stats = await index_guardian_articles(session, list(seen.values())) if seen else {
        "checked": 0, "indexed": 0, "updated": 0, "skipped": 0, "chunks_created": 0,
    }
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
    filters = RetrievalFilters()
    if from_date:
        from datetime import datetime

        filters.from_date = datetime.fromisoformat(from_date)
    if to_date:
        from datetime import datetime, time

        filters.to_date = datetime.combine(datetime.fromisoformat(to_date).date(), time.max)
    evidence: dict[str, list[ScoredChunk]] = {}
    per_subject = max(3, get_settings().rag_final_top_k // max(1, len(subjects)))
    for subject in subjects[:4]:
        evidence[subject] = await retrieve_rag(
            session, subject, filters=filters, freshness=True, rerank=True
        )
        evidence[subject] = evidence[subject][:per_subject]
    return evidence


async def build_timeline(
    session: AsyncSession,
    topic: str,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[ScoredChunk]:
    """Retrieve related chunks and order them chronologically."""
    filters = RetrievalFilters()
    if from_date:
        from datetime import datetime

        filters.from_date = datetime.fromisoformat(from_date)
    chunks = await retrieve_rag(session, topic, filters=filters, freshness=False, rerank=True)
    return sorted(
        chunks,
        key=lambda s: (s.chunk.published_at.timestamp() if s.chunk.published_at else 0),
    )


async def summarize_topic(
    session: AsyncSession, topic: str, filters: RetrievalFilters | None = None
) -> list[ScoredChunk]:
    """Evidence gathering for a sourced multi-article summary."""
    return await retrieve_rag(session, topic, filters=filters, rerank=True)


async def find_supporting_sources(
    session: AsyncSession, claim: str, candidate_article_ids: list[str]
) -> list[ScoredChunk]:
    """Given a claim, retrieve the chunks (restricted to prior sources when
    available) that support it."""
    filters = RetrievalFilters(article_ids=candidate_article_ids) if candidate_article_ids else None
    return await retrieve_rag(session, claim, filters=filters, rerank=True)
