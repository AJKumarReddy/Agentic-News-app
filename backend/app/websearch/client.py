"""Tavily web search — supplementary evidence when Guardian reporting is thin.

This is deliberately a *secondary* source. Guardian retrieval always runs
first; web results are only added when Guardian evidence is insufficient or
the user explicitly asks to look beyond the Guardian. Results carry their
real URLs and domains so citations can distinguish them from Guardian
reporting; nothing here is ever presented as Guardian journalism.
"""

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.logging import Timer, log_event
from app.services.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

API_URL = "https://api.tavily.com/search"

# Results below this relevance score are dropped rather than cited as evidence
MIN_SCORE = 0.3

# Domains that rarely carry citable reporting for a news assistant. Excluded
# so an answer never cites a video listing or a vendor doc page as news.
LOW_SIGNAL_DOMAINS = (
    "youtube.com", "m.youtube.com", "youtu.be", "tiktok.com", "instagram.com",
    "facebook.com", "pinterest.com", "quora.com", "x.com", "twitter.com",
)

# Reference lookups may legitimately return old pages; news answers should not
MAX_AGE_DAYS_NEWS = 400


class WebResult(BaseModel):
    title: str
    url: str
    content: str = ""
    published_date: str = ""
    score: float = 0.0
    source: str = ""  # domain, e.g. "reuters.com"


class WebSearchError(Exception):
    pass


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.removeprefix("www.")
    except ValueError:
        return ""


def _age_days(published: str) -> int | None:
    if not published:
        return None
    for fmt in ("%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.strptime(published[:len("Mon, 01 Jan 2026 00:00:00 GMT")].strip(), fmt)
            return (datetime.now() - parsed).days
        except ValueError:
            continue
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(published.replace("Z", "+00:00"))).days
    except ValueError:
        return None


def requested_domains(message: str) -> list[str]:
    """Domains the user named explicitly. If someone asks for YouTube, they
    should get YouTube — the quality filter must not silently substitute."""
    lowered = message.lower()
    return [d for d in LOW_SIGNAL_DOMAINS if d.split(".")[0] in lowered]


def _passes_quality_gate(
    result: "WebResult", news_like: bool, allowed: tuple[str, ...] = ()
) -> bool:
    """Drop results that shouldn't be cited: low relevance, low-signal
    domains, or (for news questions) pages years out of date."""
    if result.score and result.score < MIN_SCORE:
        return False
    is_allowed = any(result.source == d or result.source.endswith(f".{d}") for d in allowed)
    if not is_allowed and any(
        result.source == d or result.source.endswith(f".{d}") for d in LOW_SIGNAL_DOMAINS
    ):
        return False
    if not result.content.strip():
        return False
    if news_like:
        age = _age_days(result.published_date)
        if age is not None and age > MAX_AGE_DAYS_NEWS:
            return False
    return True


class TavilyClient:
    def __init__(self, api_key: str | None = None, client: httpx.AsyncClient | None = None):
        self.api_key = api_key if api_key is not None else get_settings().tavily_api_key
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def search(
        self,
        query: str,
        max_results: int = 5,
        topic: str = "news",
        days: int | None = None,
        exclude_domains: list[str] | None = None,
        allow_domains: list[str] | None = None,
    ) -> list[WebResult]:
        """Search the web. Returns [] when disabled or on failure — web search
        is supplementary and must never break a chat turn."""
        if not self.enabled or not query.strip():
            return []

        payload: dict = {
            "api_key": self.api_key,
            "query": query[:400],
            "search_depth": "basic",
            "max_results": max(1, min(10, max_results)),
            "topic": topic,
            "include_answer": False,
            "include_raw_content": False,
        }
        if days and topic == "news":
            payload["days"] = days
        if exclude_domains:
            payload["exclude_domains"] = exclude_domains

        allowed = tuple(allow_domains or ())
        cache_key = f"web:{topic}:{days}:{','.join(allowed)}:{query[:200]}:{max_results}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return [WebResult.model_validate(r) for r in cached]

        try:
            with Timer() as timer:
                response = await self._client.post(
                    API_URL,
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            if response.status_code >= 400:
                logger.warning("Tavily error %s: %s", response.status_code, response.text[:200])
                return []
            data = response.json()
        except (httpx.TimeoutException, httpx.TransportError, ValueError) as exc:
            logger.warning("Tavily request failed: %s", exc)
            return []

        raw_results = [
            WebResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                content=(item.get("content") or "")[:2000],
                published_date=item.get("published_date", "") or "",
                score=float(item.get("score", 0) or 0),
                source=_domain(item.get("url", "")),
            )
            for item in data.get("results", [])
            if item.get("url")
        ]
        results = [
            r
            for r in raw_results
            if _passes_quality_gate(r, news_like=topic == "news", allowed=allowed)
        ]

        log_event(
            logger,
            "web_search",
            query=query[:120],
            returned=len(raw_results),
            kept=len(results),
            latency_ms=timer.ms,
        )
        await cache_set(cache_key, [r.model_dump() for r in results], ttl=600)
        return results


_client: TavilyClient | None = None


def get_web_client() -> TavilyClient:
    global _client
    if _client is None:
        _client = TavilyClient()
    return _client
