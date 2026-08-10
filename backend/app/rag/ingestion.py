"""Incremental article ingestion with duplicate prevention.

Rules:
- Never embed the same Guardian article twice (keyed by Guardian article ID).
- If a stored article's content hash changed, re-chunk and re-embed it.
- Never rebuild the whole index; only unseen/updated articles are processed.
"""

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import Timer, log_event
from app.database.models import Article, Chunk
from app.database.repositories import ArticleRepository, ChunkRepository
from app.guardian.models import NormalizedArticle
from app.rag.chunker import chunk_text
from app.rag.embeddings import EmbeddingProvider, get_embedding_provider

logger = logging.getLogger(__name__)


@dataclass
class IngestionStats:
    checked: int = 0
    indexed: int = 0
    updated: int = 0
    skipped: int = 0
    chunks_created: int = 0


def needs_indexing(existing: Article | None, incoming: NormalizedArticle, embedding_model: str) -> bool:
    """Pure decision function: index when unseen, when never indexed,
    when content changed, or when the embedding model changed."""
    if existing is None or existing.first_indexed_at is None:
        return True
    if existing.content_hash != incoming.content_hash:
        return True
    if existing.embedding_model and existing.embedding_model != embedding_model:
        return True
    return False


async def ingest_articles(
    session: AsyncSession,
    articles: list[NormalizedArticle],
    embedder: EmbeddingProvider | None = None,
) -> IngestionStats:
    settings = get_settings()
    embedder = embedder or get_embedding_provider()
    article_repo = ArticleRepository(session)
    chunk_repo = ChunkRepository(session)
    stats = IngestionStats()

    with Timer() as timer:
        candidates = [a for a in articles if a.article_id and a.body_text]
        stats.checked = len(candidates)

        # One query for all existing records instead of one per article
        existing_map = {
            a.article_id: a
            for a in await article_repo.get_many([c.article_id for c in candidates])
        }

        # Pass 1: decide + chunk everything that needs indexing
        to_index: list[tuple[NormalizedArticle, bool, list]] = []
        for normalized in candidates:
            existing = existing_map.get(normalized.article_id)
            if not needs_indexing(existing, normalized, embedder.model_name):
                await article_repo.touch_checked(existing)
                stats.skipped += 1
                continue
            pieces = chunk_text(
                normalized.body_text,
                target_tokens=settings.chunk_target_tokens,
                overlap_tokens=settings.chunk_overlap_tokens,
            )
            if pieces:
                is_update = existing is not None and existing.first_indexed_at is not None
                to_index.append((normalized, is_update, pieces))

        # Pass 2: one batched embeddings call across all articles
        all_texts = [piece.text for _, _, pieces in to_index for piece in pieces]
        all_vectors = await embedder.embed_texts(all_texts)

        offset = 0
        for normalized, is_update, pieces in to_index:
            vectors = all_vectors[offset : offset + len(pieces)]
            offset += len(pieces)

            article = await article_repo.upsert(normalized)
            await chunk_repo.delete_for_article(article.article_id)
            await chunk_repo.add_all(
                [
                    Chunk(
                        article_id=article.article_id,
                        chunk_index=piece.chunk_index,
                        text=piece.text,
                        embedding=vector,
                        headline=normalized.headline,
                        published_at=normalized.published_at,
                        section=normalized.section,
                        author=normalized.author,
                        url=normalized.url,
                        tags=normalized.tags,
                    )
                    for piece, vector in zip(pieces, vectors)
                ]
            )
            await article_repo.mark_indexed(
                article, normalized.content_hash, embedder.model_name, len(pieces)
            )
            stats.chunks_created += len(pieces)
            if is_update:
                stats.updated += 1
            else:
                stats.indexed += 1

        await session.commit()

    log_event(
        logger,
        "ingestion_complete",
        articles_indexed=stats.indexed,
        articles_updated=stats.updated,
        articles_skipped=stats.skipped,
        chunks_created=stats.chunks_created,
        latency_ms=timer.ms,
    )
    return stats
