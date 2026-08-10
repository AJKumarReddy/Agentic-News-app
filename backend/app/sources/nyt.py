"""New York Times adapter (Article Search API v2).

Important limitation, surfaced deliberately rather than hidden: the NYT API
does not return article bodies. Only the abstract, lead paragraph and snippet
are available, so NYT evidence is short. Chunks are still citable and carry
real nytimes.com URLs; the synthesis prompt is told these are summaries, not
full text, so the model never implies it read the whole article.

Rate limits are tight (about 5 requests/minute, 500/day), so results are
cached and requests are spaced.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

import httpx

from app.core.config import get_settings
from app.core.logging import Timer, log_event
from app.guardian.models import NormalizedArticle
from app.guardian.normalizer import content_hash
from app.services.cache import cache_get, cache_set
from app.sources.base import NewsSource, NewsSourceError

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.nytimes.com/svc/search/v2/articlesearch.json"
TOP_STORIES_URL = "https://api.nytimes.com/svc/topstories/v2/{section}.json"

# Unified section id -> NYT desk name (Article Search)
SECTION_MAP = {
    "us-news": "U.S.",
    "world": "World",
    "politics": "Politics",
    "technology": "Technology",
    "business": "Business Day",
    "environment": "Climate",
    "science": "Science",
    "media": "Business Day",
}

# Unified section id -> Top Stories feed name
TOP_SECTION_MAP = {
    "us-news": "us",
    "world": "world",
    "politics": "politics",
    "technology": "technology",
    "business": "business",
    "environment": "climate",
    "science": "science",
    "media": "business",
}

ORDER_MAP = {"newest": "newest", "oldest": "oldest", "relevance": "relevance"}


def _iso_compact(value: str | None) -> str | None:
    """NYT expects YYYYMMDD."""
    return value.replace("-", "") if value else None


def _absolute(url: str) -> str:
    if not url:
        return ""
    return url if url.startswith("http") else f"https://www.nytimes.com/{url.lstrip('/')}"


def _extract_thumbnail(multimedia) -> str:
    """NYT has shipped several multimedia shapes: a list of objects, a list of
    URL strings, and (currently, in Article Search) a dict keyed by size.
    Handle all of them rather than assuming one."""
    if not multimedia:
        return ""
    if isinstance(multimedia, dict):
        for key in ("thumbnail", "default"):
            entry = multimedia.get(key)
            if isinstance(entry, dict) and entry.get("url"):
                return _absolute(entry["url"])
        if multimedia.get("url"):
            return _absolute(multimedia["url"])
        return ""
    if isinstance(multimedia, list):
        for media in multimedia:
            if isinstance(media, dict) and media.get("url"):
                return _absolute(media["url"])
            if isinstance(media, str) and media:
                return _absolute(media)
    return ""


class NYTSource(NewsSource):
    id = "nyt"
    name = "The New York Times"
    domain = "nytimes.com"

    #: NYT allows ~5 requests/minute; keep a floor between calls
    MIN_INTERVAL_SECONDS = 1.2

    def __init__(self, api_key: str | None = None, client: httpx.AsyncClient | None = None):
        self.api_key = api_key if api_key is not None else get_settings().nyt_api_key
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=10.0),
            headers={"User-Agent": "news-ai/1.0"},
        )
        self._lock = asyncio.Lock()
        self._last_call = 0.0
        # NYT enables each API per app. A key may be valid for Top Stories but
        # not Article Search; we detect that once and stop retrying.
        self._article_search_enabled: bool | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def owns(self, article_id: str) -> bool:
        return article_id.startswith("nyt://")

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _throttled_get(self, params: dict, url: str = SEARCH_URL) -> dict:
        params = {k: v for k, v in params.items() if v not in (None, "", [])}
        params["api-key"] = self.api_key
        async with self._lock:
            wait = self.MIN_INTERVAL_SECONDS - (time.monotonic() - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with Timer() as timer:
                    response = await self._client.get(url, params=params)
                if response.status_code == 429:
                    await asyncio.sleep(2.0 * (attempt + 1))
                    last_error = NewsSourceError("NYT rate limited", 429)
                    continue
                if response.status_code == 401:
                    raise NewsSourceError(
                        "NYT API key rejected for this endpoint — enable it for your app "
                        "at developer.nytimes.com",
                        401,
                    )
                if response.status_code >= 400:
                    raise NewsSourceError(f"NYT API error {response.status_code}", response.status_code)
                log_event(logger, "nyt_api_call", latency_ms=timer.ms)
                return response.json()
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                await asyncio.sleep(0.5 * (attempt + 1))
        raise NewsSourceError(f"NYT API unreachable: {last_error}")

    def _normalize(self, doc: dict) -> NormalizedArticle:
        headline = (doc.get("headline") or {}).get("main", "") or doc.get("abstract", "")
        byline = ((doc.get("byline") or {}).get("original") or "").removeprefix("By ").strip()

        # NYT exposes no body text; abstract + lead paragraph is all there is
        abstract = (doc.get("abstract") or "").strip()
        lead = (doc.get("lead_paragraph") or "").strip()
        snippet = (doc.get("snippet") or "").strip()
        parts = [p for p in (abstract, lead if lead != abstract else "", snippet if snippet not in (abstract, lead) else "") if p]
        body = "\n\n".join(parts)

        thumbnail = _extract_thumbnail(doc.get("multimedia"))

        published = None
        raw_date = doc.get("pub_date")
        if raw_date:
            try:
                published = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            except ValueError:
                published = None

        keywords = [k.get("value", "") for k in (doc.get("keywords") or []) if k.get("value")]

        return NormalizedArticle(
            article_id=doc.get("_id", "") or doc.get("uri", ""),
            headline=headline,
            section=doc.get("section_name", "") or doc.get("news_desk", ""),
            author=byline,
            published_at=published,
            url=doc.get("web_url", ""),
            thumbnail=thumbnail,
            trail_text=abstract,
            body_text=body,
            tags=keywords[:8],
            source="The New York Times",
            source_id=self.id,
            production_office="US",  # NYT is a US publisher
            content_hash=content_hash(body or headline),
        )

    def _normalize_top_story(self, item: dict) -> NormalizedArticle:
        """Top Stories has a different shape from Article Search."""
        byline = (item.get("byline") or "").removeprefix("By ").strip()
        abstract = (item.get("abstract") or "").strip()

        thumbnail = _extract_thumbnail(item.get("multimedia"))

        published = None
        if item.get("published_date"):
            try:
                published = datetime.fromisoformat(item["published_date"].replace("Z", "+00:00"))
            except ValueError:
                published = None

        return NormalizedArticle(
            article_id=item.get("uri", "") or item.get("url", ""),
            headline=item.get("title", ""),
            section=(item.get("section") or "").title(),
            author=byline,
            published_at=published,
            url=item.get("url", ""),
            thumbnail=thumbnail,
            trail_text=abstract,
            body_text=abstract,
            tags=[f for f in (item.get("des_facet") or [])][:8],
            source=self.name,
            source_id=self.id,
            production_office="US",
            content_hash=content_hash(abstract or item.get("title", "")),
        )

    async def top_stories(self, section: str | None = None) -> list[NormalizedArticle]:
        """Current front-page stories. Uses the Top Stories API, which most
        NYT keys have enabled by default."""
        raw = (section or "").lower()
        feed = TOP_SECTION_MAP.get(raw, raw if raw in set(TOP_SECTION_MAP.values()) else "home")
        cache_key = f"nyt:top:{feed}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return [NormalizedArticle.model_validate(a) for a in cached]

        payload = await self._throttled_get({}, url=TOP_STORIES_URL.format(section=feed))
        articles = [
            self._normalize_top_story(item)
            for item in (payload.get("results") or [])
            if item.get("url") and item.get("title")
        ]
        # Top Stories refreshes roughly every 30 minutes
        await cache_set(cache_key, [a.model_dump(mode="json") for a in articles], ttl=900)
        log_event(logger, "nyt_top_stories", section=feed, results=len(articles))
        return articles

    async def search(
        self,
        query: str = "",
        *,
        from_date: str | None = None,
        to_date: str | None = None,
        section: str | None = None,
        order_by: str = "newest",
        page: int = 1,
        page_size: int = 12,
    ) -> list[NormalizedArticle]:
        if not self.enabled:
            return []

        # A section browse with no keywords is exactly what Top Stories is
        # for; Article Search would otherwise be asked for the literal word
        # "news" and return almost nothing.
        if not query.strip():
            return (await self.top_stories(section))[:page_size]

        # Article Search is the richer endpoint but is not enabled on every
        # key. Fall back to Top Stories (keyword-filtered) rather than
        # dropping NYT from results entirely.
        if self._article_search_enabled is False:
            return await self._top_stories_fallback(query, section, page_size)
        try:
            return await self._article_search(
                query, from_date, to_date, section, order_by, page, page_size
            )
        except NewsSourceError as exc:
            if exc.status_code == 401:
                self._article_search_enabled = False
                logger.warning(
                    "NYT Article Search is not enabled for this key; using Top Stories instead"
                )
                return await self._top_stories_fallback(query, section, page_size)
            raise

    async def _top_stories_fallback(
        self, query: str, section: str | None, page_size: int
    ) -> list[NormalizedArticle]:
        articles = await self.top_stories(section)
        terms = [t for t in query.lower().split() if len(t) > 3]
        if terms:
            scored = [
                (sum(t in f"{a.headline} {a.trail_text}".lower() for t in terms), a) for a in articles
            ]
            matches = [a for score, a in sorted(scored, key=lambda p: -p[0]) if score > 0]
            if matches:
                return matches[:page_size]
            # no keyword match: better to contribute nothing than off-topic items
            return []
        return articles[:page_size]

    async def _article_search(
        self,
        query: str,
        from_date: str | None,
        to_date: str | None,
        section: str | None,
        order_by: str,
        page: int,
        page_size: int,
    ) -> list[NormalizedArticle]:
        filters = []
        if section:
            mapped = SECTION_MAP.get(section.lower())
            if mapped:
                filters.append(f'section_name:("{mapped}")')

        cache_key = f"nyt:{query}:{from_date}:{to_date}:{section}:{order_by}:{page}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return [NormalizedArticle.model_validate(a) for a in cached]

        payload = await self._throttled_get(
            {
                "q": query or "news",
                "begin_date": _iso_compact(from_date),
                "end_date": _iso_compact(to_date),
                "sort": ORDER_MAP.get(order_by, "newest"),
                "fq": " AND ".join(filters) if filters else None,
                # NYT pages are 0-based and fixed at 10 results
                "page": max(0, page - 1),
            }
        )
        docs = ((payload.get("response") or {}).get("docs")) or []
        articles = [self._normalize(d) for d in docs if d.get("web_url")][:page_size]
        await cache_set(
            cache_key,
            [a.model_dump(mode="json") for a in articles],
            ttl=get_settings().cache_ttl_seconds,
        )
        log_event(logger, "nyt_search", query=query[:80], results=len(articles))
        return articles

    async def get_article(self, article_id: str) -> NormalizedArticle | None:
        if not self.enabled:
            return None
        cache_key = f"nyt:article:{article_id}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return NormalizedArticle.model_validate(cached)
        async def from_top_stories() -> NormalizedArticle | None:
            for feed in ("home", *dict.fromkeys(TOP_SECTION_MAP.values())):
                for article in await self.top_stories(feed):
                    if article.article_id == article_id:
                        return article
            return None

        if self._article_search_enabled is False:
            return await from_top_stories()
        try:
            payload = await self._throttled_get({"fq": f'_id:("{article_id}")'})
        except NewsSourceError as exc:
            if exc.status_code == 401:
                self._article_search_enabled = False
                return await from_top_stories()
            raise
        docs = ((payload.get("response") or {}).get("docs")) or []
        if not docs:
            return None
        article = self._normalize(docs[0])
        await cache_set(cache_key, article.model_dump(mode="json"), ttl=1800)
        return article

    async def ping(self) -> bool:
        """Healthy if any NYT endpoint works — Top Stories alone is enough
        to contribute reporting."""
        if not self.enabled:
            return False
        try:
            await self.top_stories()
            return True
        except NewsSourceError:
            return False


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
