"""pgvector-backed vector store with vector + keyword search legs.

pgvector was chosen over Qdrant/Pinecone for the initial deployment: one
PostgreSQL instance serves both relational data and vectors, which keeps a
deployment simple, cheap, and transactional — one RDS instance in production,
one container locally, no extra service either way. The interface below
is small enough to reimplement against Qdrant later if scale demands it.
"""

from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from typing import Sequence

from sqlalchemy import Float, bindparam, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.database.models import Chunk
from app.sources.sections import section_match_values


def _utc(value: datetime) -> datetime:
    """Anchor a bound to UTC so it compares predictably against timestamptz."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _section_column():
    """`Chunk.section` reduced to letters and digits, for comparison.

    Publishers store a display name ("US news", "U.S."), we ask with a slug
    ("us-news"). A plain `lower(section) IN ('us-news')` matched neither, so
    every section-filtered retrieval came back empty — indistinguishable from
    a subject nobody had covered.
    """
    return func.lower(func.regexp_replace(Chunk.section, r"[^a-zA-Z0-9]", "", "g"))


@dataclass
class RetrievalFilters:
    from_date: datetime | None = None
    to_date: datetime | None = None
    sections: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    article_ids: list[str] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_iso(
        cls,
        from_date: str | None = None,
        to_date: str | None = None,
        *,
        sections: list[str] | None = None,
        tags: list[str] | None = None,
        article_ids: list[str] | None = None,
    ) -> "RetrievalFilters":
        """Build filters from ISO date strings; to_date is inclusive (end of day).

        Bounds are made UTC-aware to match `Chunk.published_at`, which is
        `timestamptz`. A naive bound is interpreted in the database session's
        timezone, so the window silently shifted by hours wherever that was not
        UTC — enough to drop articles published near midnight.
        """
        return cls(
            from_date=_utc(datetime.fromisoformat(from_date)) if from_date else None,
            to_date=_utc(datetime.combine(datetime.fromisoformat(to_date).date(), time.max))
            if to_date
            else None,
            sections=sections or [],
            tags=tags or [],
            article_ids=article_ids or [],
        )


@dataclass
class ScoredChunk:
    chunk: Chunk
    score: float


def _apply_filters(stmt, filters: RetrievalFilters | None):
    if filters is None:
        return stmt
    if filters.from_date:
        stmt = stmt.where(Chunk.published_at >= filters.from_date)
    if filters.to_date:
        stmt = stmt.where(Chunk.published_at <= filters.to_date)
    if filters.sections:
        wanted: list[str] = []
        for section in filters.sections:
            wanted.extend(section_match_values(section))
        if wanted:
            stmt = stmt.where(_section_column().in_(list(dict.fromkeys(wanted))))
    if filters.article_ids:
        stmt = stmt.where(Chunk.article_id.in_(filters.article_ids))
    if filters.source_ids:
        stmt = stmt.where(Chunk.source_id.in_(filters.source_ids))
    if filters.authors:
        stmt = stmt.where(func.lower(Chunk.author).in_([a.lower() for a in filters.authors]))
    if filters.tags:
        # JSONB containment: chunk.tags must include at least one requested tag
        from sqlalchemy import or_

        stmt = stmt.where(or_(*[Chunk.tags.contains([tag]) for tag in filters.tags]))
    return stmt


async def vector_search(
    session: AsyncSession,
    query_embedding: Sequence[float],
    top_k: int = 20,
    filters: RetrievalFilters | None = None,
) -> list[ScoredChunk]:
    distance = Chunk.embedding.cosine_distance(list(query_embedding)).label("distance")
    # embeddings are ranked in SQL; never hydrate the 1536-dim vectors
    stmt = select(Chunk, distance).options(defer(Chunk.embedding)).order_by(distance.asc()).limit(top_k)
    stmt = _apply_filters(stmt, filters)
    result = await session.execute(stmt)
    return [ScoredChunk(chunk=row[0], score=1.0 - float(row[1])) for row in result.all()]


async def keyword_search(
    session: AsyncSession,
    query: str,
    top_k: int = 20,
    filters: RetrievalFilters | None = None,
) -> list[ScoredChunk]:
    if not query.strip():
        return []
    tsquery = func.plainto_tsquery("english", bindparam("kw_query", query))
    tsvector = func.to_tsvector("english", Chunk.text)
    rank = func.ts_rank_cd(tsvector, tsquery).cast(Float).label("rank")
    stmt = (
        select(Chunk, rank)
        .options(defer(Chunk.embedding))
        .where(tsvector.op("@@")(tsquery))
        .order_by(text("rank DESC"))
        .limit(top_k)
    )
    stmt = _apply_filters(stmt, filters)
    result = await session.execute(stmt)
    return [ScoredChunk(chunk=row[0], score=float(row[1])) for row in result.all()]
