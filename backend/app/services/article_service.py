"""Article detail + AI 'article intelligence' (summary, key points, entities,
topics, dates, related articles)."""

import logging
from typing import Any

from app.sources import source_for_article
from app.sources.base import NewsSourceError
from app.guardian.models import NormalizedArticle
from app.llm.client import extract_json, get_chat_model, response_text
from app.llm.prompts import ARTICLE_INTELLIGENCE_PROMPT
from app.services.cache import cache_get, cache_set

logger = logging.getLogger(__name__)


async def get_article(article_id: str) -> NormalizedArticle:
    key = f"guardian:article:{article_id}"
    cached = await cache_get(key)
    if cached:
        return NormalizedArticle.model_validate(cached)
    # Our own index first: anything reachable from search is already stored,
    # so this avoids a publisher round trip and keeps working for sources
    # whose article-lookup endpoint isn't available on the current key.
    stored = await _from_index(article_id)
    if stored is not None:
        await cache_set(key, stored.model_dump(mode="json"), ttl=1800)
        return stored

    source = source_for_article(article_id)
    if source is None:
        raise NewsSourceError(f"No configured source owns {article_id}", 404)
    article = await source.get_article(article_id)
    if article is None:
        raise NewsSourceError(
            f"{source.name} does not expose this article through its API", 404
        )
    await cache_set(key, article.model_dump(mode="json"), ttl=1800)
    return article


async def _from_index(article_id: str) -> NormalizedArticle | None:
    from app.database.models import Article
    from app.database.repositories import to_normalized
    from app.database.session import SessionFactory

    async with SessionFactory() as session:
        row = await session.get(Article, article_id)
        # a row with no text is a search-fallback stub, not a readable article
        if row is None or not (row.body_text or row.trail_text):
            return None
        return to_normalized(row)


async def get_related_articles(article: NormalizedArticle, limit: int = 5) -> list[NormalizedArticle]:
    """Related coverage via the article's keyword tags."""
    """Related coverage, drawn from every enabled publisher."""
    topic = article.tags[0] if article.tags else article.headline
    if not topic:
        return []
    try:
        from app.services.search_service import search_news

        result = await search_news(query=topic.split("/")[-1], order_by="newest", page_size=limit + 2)
        return [a for a in result.articles if a.article_id != article.article_id][:limit]
    except Exception:  # noqa: BLE001 - related articles are a nicety
        return []


async def analyze_article(article: NormalizedArticle) -> dict[str, Any]:
    key = f"intel:{article.article_id}:{article.content_hash[:12]}"
    cached = await cache_get(key)
    if cached:
        return cached

    prompt = ARTICLE_INTELLIGENCE_PROMPT.format(
        headline=article.headline,
        published_at=article.published_at.isoformat() if article.published_at else "unknown",
        body=article.body_text[:24000],
    )
    analysis: dict[str, Any] = {
        "summary": "", "key_points": [], "entities": [], "topics": [], "important_dates": [],
    }
    try:
        response = await get_chat_model(temperature=0, max_tokens=900).ainvoke(prompt)
        parsed = extract_json(response_text(response), default={})
        for field in analysis:
            if field in parsed:
                analysis[field] = parsed[field]
    except Exception:
        logger.warning("Article analysis failed", exc_info=True)
        analysis["summary"] = article.trail_text or "Analysis unavailable."

    await cache_set(key, analysis, ttl=3600)
    return analysis
