"""Hybrid retrieval: vector similarity + keyword matching fused with
Reciprocal Rank Fusion, plus metadata filtering and recency weighting."""

import logging
import math
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import Timer, log_event
from app.rag.embeddings import get_embedding_provider
from app.rag.vector_store import RetrievalFilters, ScoredChunk, keyword_search, vector_search

logger = logging.getLogger(__name__)

RRF_K = 60


def rrf_merge(result_lists: list[list[ScoredChunk]]) -> dict[int, float]:
    """Reciprocal Rank Fusion across ranked lists → chunk_id -> fused score."""
    scores: dict[int, float] = {}
    for results in result_lists:
        for rank, scored in enumerate(results):
            scores[scored.chunk.id] = scores.get(scored.chunk.id, 0.0) + 1.0 / (RRF_K + rank + 1)
    return scores


def recency_boost(published_at: datetime | None, weight: float, half_life_days: float = 7.0) -> float:
    if published_at is None:
        return 0.0
    now = datetime.now(timezone.utc)
    published = published_at if published_at.tzinfo else published_at.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - published).total_seconds() / 86400)
    return weight * math.exp(-age_days / half_life_days)


async def hybrid_retrieve(
    session: AsyncSession,
    query: str,
    filters: RetrievalFilters | None = None,
    top_k: int | None = None,
    freshness: bool = False,
) -> list[ScoredChunk]:
    settings = get_settings()
    top_k = top_k or settings.rag_initial_top_k

    with Timer() as timer:
        query_embedding = await get_embedding_provider().embed_query(query)
        vector_results = await vector_search(session, query_embedding, top_k=top_k, filters=filters)
        keyword_results = await keyword_search(session, query, top_k=top_k, filters=filters)

        fused = rrf_merge([vector_results, keyword_results])
        by_id = {s.chunk.id: s.chunk for s in vector_results + keyword_results}

        # Recency matters for news; freshness-sensitive queries weight it higher
        weight = 0.02 if freshness else 0.005
        results = [
            ScoredChunk(chunk=by_id[cid], score=score + recency_boost(by_id[cid].published_at, weight))
            for cid, score in fused.items()
        ]
        results.sort(key=lambda s: s.score, reverse=True)
        results = results[:top_k]

    log_event(
        logger,
        "rag_retrieval",
        retrieved_chunks=len(results),
        vector_hits=len(vector_results),
        keyword_hits=len(keyword_results),
        retrieval_latency=timer.ms,
    )
    return results
