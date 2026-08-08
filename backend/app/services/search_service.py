"""Guardian search with Redis caching — news goes stale, so TTLs are short."""

import hashlib
import json

from app.core.config import get_settings
from app.guardian.client import get_guardian_client
from app.guardian.models import GuardianSearchResult
from app.services.cache import cache_get, cache_set


def _cache_key(params: dict) -> str:
    digest = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:24]
    return f"guardian:search:{digest}"


async def search_news(
    query: str = "",
    from_date: str | None = None,
    to_date: str | None = None,
    section: str | None = None,
    tag: str | None = None,
    author: str | None = None,
    order_by: str = "newest",
    page: int = 1,
    page_size: int | None = None,
) -> GuardianSearchResult:
    params = {
        "q": query, "from": from_date, "to": to_date, "section": section,
        "tag": tag, "author": author, "order": order_by, "page": page, "size": page_size,
    }
    key = _cache_key(params)
    cached = await cache_get(key)
    if cached:
        return GuardianSearchResult.model_validate(cached)

    result = await get_guardian_client().search(
        query=query,
        from_date=from_date,
        to_date=to_date,
        section=section,
        tag=tag,
        author=author,
        order_by=order_by,
        page=page,
        page_size=page_size,
    )
    await cache_set(key, result.model_dump(mode="json"), ttl=get_settings().cache_ttl_seconds)
    return result
