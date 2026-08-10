import asyncio

from fastapi import APIRouter, Query

from app.services.article_service import analyze_article, get_article, get_related_articles
from app.services.search_service import search_news

router = APIRouter(prefix="/news", tags=["news"])

# GuardianAPIError raised below is translated to 404/502 by the
# global exception handler in app.main.


@router.get("/search")
async def search(
    q: str = Query(default="", max_length=300),
    from_date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    to_date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    section: str | None = Query(default=None, max_length=64),
    tag: str | None = Query(default=None, max_length=128),
    author: str | None = Query(default=None, max_length=128),
    order_by: str = Query(default="newest", pattern="^(newest|oldest|relevance)$"),
    page: int = Query(default=1, ge=1, le=100),
    page_size: int = Query(default=12, ge=1, le=50),
):
    result = await search_news(
        query=q,
        from_date=from_date,
        to_date=to_date,
        section=section,
        tag=tag,
        author=author,
        order_by=order_by,
        page=page,
        page_size=page_size,
    )
    # cards never render bodies — don't ship ~100 KB of dead payload per page
    return result.model_dump(mode="json", exclude={"articles": {"__all__": {"body_text"}}})


@router.get("/article/{article_id:path}/intelligence")
async def article_intelligence(article_id: str):
    article = await get_article(article_id)
    analysis, related = await asyncio.gather(
        analyze_article(article), get_related_articles(article)
    )
    return {
        "article": article.model_dump(mode="json", exclude={"body_text"}),
        "analysis": analysis,
        "related": [r.model_dump(mode="json", exclude={"body_text"}) for r in related],
    }


@router.get("/article/{article_id:path}")
async def article_detail(article_id: str):
    article = await get_article(article_id)
    return article.model_dump(mode="json")
