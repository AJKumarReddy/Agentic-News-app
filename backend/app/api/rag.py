"""Retrieval and ingestion tooling for operators.

Every endpoint here spends money — an embedding per retrieve, publisher
requests plus embeddings per ingest — and none of them is called by the UI.
They are gated: closed in production unless ADMIN_API_KEY is set and sent as
X-Admin-Key. See app.core.security.require_admin.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import tools
from app.core.security import require_admin
from app.database.session import get_session
from app.rag.vector_store import RetrievalFilters

router = APIRouter(prefix="/rag", tags=["rag"], dependencies=[Depends(require_admin)])


ISO_DATE = r"^\d{4}-\d{2}-\d{2}$"


def _validate_dates(value: str | None) -> str | None:
    """Reject a date the retrieval layer cannot parse.

    `RetrievalFilters.from_iso` calls `datetime.fromisoformat` directly, so an
    unparseable value ("nonsense") or an impossible one ("2026-13-45") raised
    a ValueError out of the request handler and returned a 500. The pattern
    alone catches the shape; `date.fromisoformat` catches the rest.
    """
    if value is None:
        return None
    from datetime import date

    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError("must be a real calendar date in YYYY-MM-DD form") from exc


class RetrieveRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    from_date: str | None = Field(default=None, pattern=ISO_DATE)
    to_date: str | None = Field(default=None, pattern=ISO_DATE)
    sections: list[str] = Field(default_factory=list, max_length=10)
    tags: list[str] = Field(default_factory=list, max_length=10)
    article_ids: list[str] = Field(default_factory=list, max_length=25)
    top_k: int = Field(default=8, ge=1, le=30)
    freshness: bool = False
    rerank: bool = True

    _dates = field_validator("from_date", "to_date")(_validate_dates)


class IngestRequest(BaseModel):
    query: str = Field(default="", max_length=300)
    article_ids: list[str] = Field(default_factory=list, max_length=25)
    from_date: str | None = Field(default=None, pattern=ISO_DATE)
    to_date: str | None = Field(default=None, pattern=ISO_DATE)
    section: str | None = Field(default=None, max_length=64)

    _dates = field_validator("from_date", "to_date")(_validate_dates)


@router.post("/retrieve")
async def retrieve(request: RetrieveRequest, session: AsyncSession = Depends(get_session)):
    filters = RetrievalFilters.from_iso(
        request.from_date,
        request.to_date,
        sections=request.sections,
        tags=request.tags,
        article_ids=request.article_ids,
    )
    chunks = await tools.retrieve_rag(
        session,
        request.query,
        filters=filters,
        top_k=request.top_k,
        freshness=request.freshness,
        rerank=request.rerank,
    )
    return {
        "results": [
            {
                "article_id": s.chunk.article_id,
                "chunk_index": s.chunk.chunk_index,
                "headline": s.chunk.headline,
                "url": s.chunk.url,
                "section": s.chunk.section,
                "published_at": s.chunk.published_at,
                "score": s.score,
                "text": s.chunk.text,
            }
            for s in chunks
        ]
    }


@router.post("/ingest")
async def ingest(request: IngestRequest, session: AsyncSession = Depends(get_session)):
    """Ingest by explicit article IDs and/or a Guardian search query."""
    return await tools.fetch_and_index(
        session,
        queries=[request.query] if request.query else [],
        article_ids=request.article_ids,
        from_date=request.from_date,
        to_date=request.to_date,
        section=request.section,
    )
