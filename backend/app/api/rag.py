from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import tools
from app.database.session import get_session
from app.rag.vector_store import RetrievalFilters

router = APIRouter(prefix="/rag", tags=["rag"])


class RetrieveRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    from_date: str | None = None
    to_date: str | None = None
    sections: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    article_ids: list[str] = Field(default_factory=list)
    top_k: int = Field(default=8, ge=1, le=30)
    freshness: bool = False
    rerank: bool = True


class IngestRequest(BaseModel):
    query: str = Field(default="", max_length=300)
    article_ids: list[str] = Field(default_factory=list, max_length=25)
    from_date: str | None = None
    to_date: str | None = None
    section: str | None = None


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
