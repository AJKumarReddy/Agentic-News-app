"""TheNewsAPI adapter (api.thenewsapi.com).

Unlike the Guardian and the NYT this is not a masthead but an aggregator over
thousands of outlets, which is the point of adding it: it reaches stories
neither paper ran. Three consequences shape everything below.

**No article bodies.** Like the NYT feed, only a description and a snippet come
back, so this source contributes short evidence. Chunks stay citable and carry
the publisher's real URL; nothing here ever implies we read the full text.

**The citation is not "TheNewsAPI".** Each article names its actual publisher,
and that is what `source` carries — "cnn.com", not the aggregator that relayed
it. Citing the pipe instead of the newsroom would be misleading. `source_id`
stays `thenewsapi`, since that is who fetched it.

**A very small budget.** The free plan allows 100 requests a day and at most 3
articles per request, against scheduled ingestion that ticks every five
minutes. Every call therefore checks a shared daily counter first (see
`app.sources.quota`), and background ingestion is cut off before interactive
search is. Running out is not an error condition: the call raises
`NewsSourceError` like any other failure, and `search_service` answers from the
articles we already stored — the same path an unreachable publisher takes.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta

import httpx

from app.core.config import get_settings
from app.core.logging import Timer, log_event
from app.guardian.models import NormalizedArticle
from app.guardian.normalizer import content_hash
from app.services.cache import cache_get, cache_set
from app.sources.base import NewsSource, NewsSourceError, SourceResult
from app.sources.quota import background_ingest, spend, spent_today

logger = logging.getLogger(__name__)

BASE_URL = "https://api.thenewsapi.com/v1/news"
SEARCH_URL = f"{BASE_URL}/all"
# Curated top stories. `/all` sorted by date is the entire firehose newest
# first, which on a keyword-less browse is dominated by whatever CMS published
# most recently — a live check returned three fda.gov boilerplate pages
# ("Overview & Basics") as the top US news. `/top` is the same shape and the
# same filters over an editorially selected set, which is what a browse wants.
# Exactly the reason the NYT adapter reaches for Top Stories; see nyt.py.
# (`/headlines` would be the third option but is 403 on the free plan.)
TOP_URL = f"{BASE_URL}/top"
ARTICLE_URL = BASE_URL + "/uuid/{uuid}"

#: Ids are prefixed so `owns()` can claim them. Guardian ids are bare paths and
#: its `owns()` claims anything without a scheme, so a scheme is what keeps
#: routing honest between the three sources.
ID_PREFIX = "thenewsapi://"

# Unified section slug -> TheNewsAPI category. Its vocabulary is ten broad
# buckets, so several of our sections necessarily share one.
SECTION_MAP = {
    "us-news": "general",
    "world": "general",
    "politics": "politics",
    "technology": "tech",
    "business": "business",
    "money": "business",
    "environment": "science",
    "science": "science",
    "society": "health",
    "sport": "sports",
    "football": "sports",
    "culture": "entertainment",
    "film": "entertainment",
    "books": "entertainment",
    "music": "entertainment",
    "fashion": "entertainment",
    "travel": "travel",
    "food": "food",
    "media": "general",
    "commentisfree": "politics",
}

# The way back, used when storing an article. The rest of the app compares
# sections through `app.sources.sections`, whose vocabulary is the Guardian's —
# so "tech" is written down as "Technology" and a section filter finds it.
# "general" has no honest equivalent and is deliberately not dressed up as
# World; it stays a grab-bag under its own name.
CATEGORY_SECTION = {
    "general": "News",
    "politics": "Politics",
    "tech": "Technology",
    "business": "Business",
    "science": "Science",
    "health": "Society",
    "sports": "Sport",
    "entertainment": "Culture",
    "travel": "Travel",
    "food": "Food",
}


def _pick_category(categories: list[str], requested: str | None) -> str:
    """Which of an article's categories to file it under.

    Articles carry several, and "general" leads more often than not — a live
    response to a `categories=politics` browse tags them `["general",
    "politics"]`. Taking the first would file the whole page under the catch-all
    and a later filter for politics would not find one of them, which is the
    section filter appearing to be broken on this source alone.

    So: honour what was asked for when the article actually carries it, then
    prefer anything more specific than the catch-all, and only fall back to
    "general" when that is genuinely all the article has.
    """
    if not categories:
        return ""
    if requested and requested in categories:
        return requested
    specific = [c for c in categories if c != "general"]
    return specific[0] if specific else categories[0]


def _published_before(to_date: str | None) -> str | None:
    """`published_before` is exclusive, so a bare `to_date` drops that whole
    day — the Guardian and the NYT both treat their end date as inclusive, and
    a range that quietly means something different per source is a bug that
    only ever shows up as missing articles."""
    if not to_date:
        return None
    try:
        return (datetime.fromisoformat(to_date).date() + timedelta(days=1)).isoformat()
    except ValueError:
        return None


class TheNewsAPISource(NewsSource):
    id = "thenewsapi"
    name = "TheNewsAPI"
    # Deliberately empty: `registry.source_domains()` builds the web-search
    # exclusion list, and an aggregator has no one domain to exclude. The
    # articles live on the publishers' own sites, not on thenewsapi.com.
    domain = ""

    #: Politeness floor between calls. The daily budget is the real constraint;
    #: this only stops a burst from tripping the per-second limit.
    MIN_INTERVAL_SECONDS = 0.5

    def __init__(self, api_key: str | None = None, client: httpx.AsyncClient | None = None):
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.thenewsapi_api_key
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=10.0),
            headers={"User-Agent": "source-news/1.0"},
        )
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @property
    def bulk_efficient(self) -> bool:
        """No. The free plan returns three articles per request against a
        hundred requests a day, so indexing from here buys ~17x less per
        request than the Guardian's fifty. Kept off the scheduled sweep so the
        whole budget stays available to searches someone is waiting on, where
        this source earns its place on breadth rather than volume."""
        return False

    def owns(self, article_id: str) -> bool:
        return article_id.startswith(ID_PREFIX)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _budget(self) -> int:
        """Today's ceiling for this caller.

        Ingestion runs unattended and can afford to miss a tick; somebody
        waiting on a search cannot. So the background job is held to the budget
        minus the reserve and stops while there is still quota left for the
        interactive path.
        """
        settings = get_settings()
        if background_ingest.get():
            return settings.thenewsapi_daily_budget - settings.thenewsapi_interactive_reserve
        return settings.thenewsapi_daily_budget

    async def _get(self, url: str, params: dict) -> dict:
        if not await spend(self.id, self._budget()):
            caller = "ingestion" if background_ingest.get() else "search"
            raise NewsSourceError(f"TheNewsAPI daily budget exhausted for {caller}")

        params = {k: v for k, v in params.items() if v not in (None, "", [])}
        params["api_token"] = self.api_key

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
                    await asyncio.sleep(1.0 * (attempt + 1))
                    last_error = NewsSourceError("TheNewsAPI rate limited", 429)
                    continue
                if response.status_code in (401, 403):
                    raise NewsSourceError("TheNewsAPI key rejected", response.status_code)
                if response.status_code == 402:
                    # the plan's own ceiling, reached before our counter did
                    raise NewsSourceError("TheNewsAPI plan quota exhausted", 402)
                if response.status_code >= 400:
                    raise NewsSourceError(
                        f"TheNewsAPI error {response.status_code}", response.status_code
                    )
                log_event(logger, "thenewsapi_call", latency_ms=timer.ms)
                return response.json()
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                await asyncio.sleep(0.5 * (attempt + 1))
        raise NewsSourceError(f"TheNewsAPI unreachable: {last_error}")

    def _normalize(self, item: dict, requested: str | None = None) -> NormalizedArticle:
        categories = [c for c in (item.get("categories") or []) if c]
        category = _pick_category(categories, requested)

        description = (item.get("description") or "").strip()
        snippet = (item.get("snippet") or "").strip()
        # the snippet is usually the opening of the same description; keep it
        # only when it actually adds something
        body = "\n\n".join(p for p in (description, snippet if snippet != description else "") if p)

        published = None
        raw_date = item.get("published_at")
        if raw_date:
            try:
                published = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            except ValueError:
                published = None

        keywords = [k.strip() for k in (item.get("keywords") or "").split(",") if k.strip()]

        return NormalizedArticle(
            article_id=ID_PREFIX + (item.get("uuid") or ""),
            headline=item.get("title", ""),
            section=CATEGORY_SECTION.get(category, category.title()),
            author="",  # not exposed by this API
            published_at=published,
            url=item.get("url", ""),
            thumbnail=item.get("image_url") or "",
            trail_text=description,
            body_text=body,
            tags=keywords[:8],
            # the newsroom that reported it, not the pipe that relayed it
            source=item.get("source") or self.name,
            source_id=self.id,
            production_office=(item.get("locale") or "").upper(),
            content_hash=content_hash(body or item.get("title", "")),
        )

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
        result = await self.search_page(
            query,
            from_date=from_date,
            to_date=to_date,
            section=section,
            order_by=order_by,
            page=page,
            page_size=page_size,
        )
        return result.articles

    async def search_page(
        self,
        query: str = "",
        *,
        from_date: str | None = None,
        to_date: str | None = None,
        section: str | None = None,
        order_by: str = "newest",
        page: int = 1,
        page_size: int = 12,
    ) -> SourceResult:
        if not self.enabled:
            return SourceResult()

        settings = get_settings()
        # The plan caps this hard and rejects anything larger, so the caller's
        # page size is a ceiling we are usually nowhere near.
        limit = max(1, min(page_size, settings.thenewsapi_page_size))
        category = SECTION_MAP.get((section or "").lower()) if section else None

        # No keywords means "show me the news", which is what /top is for.
        # A locale only makes sense there — "top stories" is regional by
        # nature — and it reuses the edition the app already prefers rather
        # than adding a knob. A keyword search stays unlocalised: pinning
        # "trump" to US outlets would be a filter, and the edition preference
        # is deliberately only ever a ranking nudge.
        browse = not query.strip()
        locale = settings.preferred_production_office.lower() if browse else None

        cache_key = (
            f"thenewsapi:{query}:{from_date}:{to_date}:{category}:"
            f"{order_by}:{page}:{limit}:{locale}"
        )
        cached = await cache_get(cache_key)
        if cached is not None:
            return SourceResult(
                articles=[NormalizedArticle.model_validate(a) for a in cached["articles"]],
                total=cached["total"],
                pages=cached["pages"],
            )

        # Same day at both ends is a single-day query, which the API expresses
        # exactly — and exact beats a two-sided range built on an exclusive bound.
        same_day = bool(from_date) and from_date == to_date
        payload = await self._get(
            TOP_URL if browse else SEARCH_URL,
            {
                "search": query or None,
                "language": "en",
                "locale": locale,
                "categories": category,
                "published_on": from_date if same_day else None,
                "published_after": None if same_day else from_date,
                "published_before": None if same_day else _published_before(to_date),
                # There is no ascending sort on this API. "oldest" still asks
                # for published_at and lets search_service.merge() do the
                # ascending sort it already does across every source.
                #
                # Omitted entirely on /top, whose whole value is its own
                # editorial ordering — re-sorting it by date would hand back
                # the firehose we switched away from.
                "sort": None
                if browse
                else ("relevance_score" if order_by == "relevance" else "published_at"),
                "page": max(1, page),
                "limit": limit,
            },
        )

        articles = [
            self._normalize(item, requested=category)
            for item in (payload.get("data") or [])
            if item.get("uuid") and item.get("url") and item.get("title")
        ]
        meta = payload.get("meta") or {}
        found = meta.get("found") if isinstance(meta.get("found"), int) else len(articles)
        pages = max(1, -(-found // limit)) if found else 0

        await cache_set(
            cache_key,
            {
                "articles": [a.model_dump(mode="json") for a in articles],
                "total": found,
                "pages": pages,
            },
            ttl=settings.cache_ttl_seconds,
        )
        log_event(logger, "thenewsapi_search", query=query[:80], results=len(articles), found=found)
        return SourceResult(articles=articles, total=found, pages=pages)

    async def get_article(self, article_id: str) -> NormalizedArticle | None:
        if not self.enabled:
            return None
        uuid = article_id.removeprefix(ID_PREFIX)
        if not uuid:
            return None

        cache_key = f"thenewsapi:article:{uuid}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return NormalizedArticle.model_validate(cached)

        payload = await self._get(ARTICLE_URL.format(uuid=uuid), {})
        # this endpoint answers with the article itself, not a data list
        item = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        if not item or not item.get("uuid"):
            return None
        article = self._normalize(item)
        await cache_set(cache_key, article.model_dump(mode="json"), ttl=1800)
        return article

    async def ping(self) -> bool:
        """Healthy when configured and still inside today's budget.

        Deliberately does not call the API. /api/health is polled continuously
        and caches source status for only 60 seconds, so a real probe would
        spend on the order of 1400 requests a day against a budget of 100 — the
        health check alone would take the source down. The cost is that a
        rejected key reads as available here until a real search reports it.
        """
        if not self.enabled:
            return False
        return await spent_today(self.id) < get_settings().thenewsapi_daily_budget
