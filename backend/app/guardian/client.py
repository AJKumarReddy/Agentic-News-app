"""Async client for the Guardian Open Platform Content API.

Docs: https://open-platform.theguardian.com/documentation/
"""

import asyncio
import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import Timer, log_event
from app.guardian.models import GuardianSearchResult, NormalizedArticle
from app.guardian.normalizer import normalize_article

logger = logging.getLogger(__name__)

DEFAULT_SHOW_FIELDS = "headline,trailText,body,bodyText,thumbnail,byline,publication,shortUrl"
DEFAULT_SHOW_TAGS = "contributor,keyword"


class GuardianAPIError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class GuardianClient:
    BASE_URL = "https://content.guardianapis.com"

    def __init__(self, api_key: str | None = None, client: httpx.AsyncClient | None = None):
        self.api_key = api_key if api_key is not None else get_settings().guardian_api_key
        self._client = client or httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=httpx.Timeout(20.0, connect=10.0),
            headers={"User-Agent": "guardian-ai-news-assistant/1.0"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        params = {k: v for k, v in params.items() if v not in (None, "", [])}
        params["api-key"] = self.api_key
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with Timer() as timer:
                    response = await self._client.get(path, params=params)
                if response.status_code == 429:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    last_error = GuardianAPIError("Guardian API rate limited", 429)
                    continue
                if response.status_code >= 400:
                    raise GuardianAPIError(
                        f"Guardian API error {response.status_code}", response.status_code
                    )
                payload = response.json().get("response", {})
                if payload.get("status") not in (None, "ok"):
                    raise GuardianAPIError(f"Guardian API status: {payload.get('status')}")
                log_event(logger, "guardian_api_call", path=path, guardian_api_latency=timer.ms)
                return payload
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                await asyncio.sleep(0.5 * (attempt + 1))
        raise GuardianAPIError(f"Guardian API unreachable: {last_error}")

    async def search(
        self,
        query: str = "",
        *,
        from_date: str | None = None,
        to_date: str | None = None,
        section: str | None = None,
        tag: str | None = None,
        author: str | None = None,
        order_by: str = "relevance",  # newest | oldest | relevance
        page: int = 1,
        page_size: int | None = None,
        show_fields: str = DEFAULT_SHOW_FIELDS,
        show_tags: str = DEFAULT_SHOW_TAGS,
    ) -> GuardianSearchResult:
        settings = get_settings()
        if author:
            # Guardian models authors as contributor tags: profile/<slug>
            slug = author.strip().lower().replace(" ", "")
            tag = f"profile/{slug}" if not tag else f"{tag},profile/{slug}"
        payload = await self._get(
            "/search",
            {
                "q": query,
                "from-date": from_date,
                "to-date": to_date,
                "section": section,
                "tag": tag,
                "order-by": order_by,
                "page": max(1, page),
                "page-size": min(50, page_size or settings.guardian_page_size),
                "show-fields": show_fields,
                "show-tags": show_tags,
            },
        )
        articles = [normalize_article(item) for item in payload.get("results", [])]
        result = GuardianSearchResult(
            total=payload.get("total", 0),
            page=payload.get("currentPage", 1),
            pages=payload.get("pages", 1),
            page_size=payload.get("pageSize", page_size or settings.guardian_page_size),
            articles=articles,
        )
        log_event(logger, "guardian_search", query=query, guardian_articles_found=len(articles))
        return result

    async def get_article(self, article_id: str) -> NormalizedArticle:
        payload = await self._get(
            f"/{article_id.lstrip('/')}",
            {"show-fields": DEFAULT_SHOW_FIELDS, "show-tags": DEFAULT_SHOW_TAGS},
        )
        content = payload.get("content")
        if not content:
            raise GuardianAPIError(f"Article not found: {article_id}", 404)
        return normalize_article(content)

    async def ping(self) -> bool:
        try:
            await self._get("/search", {"page-size": 1})
            return True
        except GuardianAPIError:
            return False


_client: GuardianClient | None = None


def get_guardian_client() -> GuardianClient:
    global _client
    if _client is None:
        _client = GuardianClient()
    return _client
