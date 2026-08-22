"""News source abstraction.

Every provider returns the same NormalizedArticle, so retrieval, chunking,
citations and the UI stay source-agnostic. Adding a publisher means adding
one adapter here — nothing downstream changes.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.guardian.models import NormalizedArticle
from app.sources.quota import background_ingest, claim


@dataclass
class SourceResult:
    """One page from a publisher, with what it reports about the whole set.

    total/pages are best effort: publishers cap and estimate differently, so
    these are only ever used to size pagination, never to claim exact counts.
    """

    articles: list[NormalizedArticle] = field(default_factory=list)
    total: int = 0
    pages: int = 1


class NewsSourceError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class NewsSource(ABC):
    #: stable machine id, also the prefix used in article ids where needed
    id: str = ""
    #: display name used in citations
    name: str = ""
    #: canonical site domain, used to keep web search from duplicating us
    domain: str = ""

    @property
    def enabled(self) -> bool:
        return True

    @property
    def daily_budget(self) -> int:
        """Requests this publisher's plan allows per UTC day.

        Per source, because publishers meter differently: 500 a day on a
        Guardian or NYT developer key, 2,500 on TheNewsAPI's Basic plan. An
        adapter declares its own from settings, so changing plan is a config
        change and never a code one.

        0 — the default — means this source is not metered here. A ceiling
        invented for a publisher whose plan nobody has checked would throttle
        it for no reason, which is worse than not counting.
        """
        return 0

    @property
    def interactive_reserve(self) -> int:
        """How much of `daily_budget` is kept for requests a person is waiting
        on. Background ingestion stops at budget - reserve; interactive work
        runs to the full budget."""
        return 0

    async def claim_request(self) -> None:
        """Charge one request to this publisher's budget, or refuse.

        Called by an adapter immediately before it actually goes to the
        network — after any cache lookup, since a cached answer costs the
        publisher nothing and must not cost budget either.

        Running out is not an error condition: `NewsSourceError` is what every
        other publisher failure raises, and `search_service` already answers
        from the articles we stored, the same path an unreachable publisher
        takes.
        """
        if await claim(self.id, self.daily_budget, self.interactive_reserve):
            return
        caller = "ingestion" if background_ingest.get() else "search"
        raise NewsSourceError(f"{self.name} daily budget exhausted for {caller}")

    @property
    def bulk_efficient(self) -> bool:
        """Whether this source is worth spending on background indexing.

        A source that returns a handful of articles per request buys very
        little index for each unit of a metered budget, and every request it
        spends there is one a reader waiting on a search cannot have. Such a
        source returns False and is used only on the interactive path, where
        its breadth is what matters and the volume is not.
        """
        return True

    @abstractmethod
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
        """Search this publisher. Raises NewsSourceError on failure."""

    @abstractmethod
    async def get_article(self, article_id: str) -> NormalizedArticle | None:
        """Fetch one article by this source's id, or None if not found."""

    @abstractmethod
    def owns(self, article_id: str) -> bool:
        """Whether an article id belongs to this source."""

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
        """Search and report pagination. Sources that know their totals
        override this; the default reports only what it returned."""
        articles = await self.search(
            query,
            from_date=from_date,
            to_date=to_date,
            section=section,
            order_by=order_by,
            page=page,
            page_size=page_size,
        )
        return SourceResult(articles=articles, total=len(articles), pages=1 if articles else 0)

    async def ping(self) -> bool:
        try:
            await self.search(page_size=1)
            return True
        except NewsSourceError:
            return False

    async def aclose(self) -> None:
        return None
