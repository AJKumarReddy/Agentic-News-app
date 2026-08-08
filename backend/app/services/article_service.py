"""Article detail + AI 'article intelligence' (summary, key points, entities,
topics, dates, related articles)."""

import json
import logging
import re
from typing import Any

from app.guardian.client import GuardianAPIError, get_guardian_client
from app.guardian.models import NormalizedArticle
from app.llm.client import get_chat_model
from app.llm.prompts import ARTICLE_INTELLIGENCE_PROMPT
from app.services.cache import cache_get, cache_set

logger = logging.getLogger(__name__)


async def get_article(article_id: str) -> NormalizedArticle:
    key = f"guardian:article:{article_id}"
    cached = await cache_get(key)
    if cached:
        return NormalizedArticle.model_validate(cached)
    article = await get_guardian_client().get_article(article_id)
    await cache_set(key, article.model_dump(mode="json"), ttl=1800)
    return article


async def get_related_articles(article: NormalizedArticle, limit: int = 5) -> list[NormalizedArticle]:
    """Related coverage via the article's keyword tags."""
    if not article.tags:
        return []
    try:
        result = await get_guardian_client().search(
            tag=article.tags[0], order_by="newest", page_size=limit + 1
        )
        return [a for a in result.articles if a.article_id != article.article_id][:limit]
    except GuardianAPIError:
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
        content = response.content if hasattr(response, "content") else str(response)
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            for field in analysis:
                if field in parsed:
                    analysis[field] = parsed[field]
    except Exception:
        logger.warning("Article analysis failed", exc_info=True)
        analysis["summary"] = article.trail_text or "Analysis unavailable."

    await cache_set(key, analysis, ttl=3600)
    return analysis
