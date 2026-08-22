"""News source abstraction.

Every provider returns the same NormalizedArticle, so retrieval, chunking,
citations and the UI stay source-agnostic. Adding a publisher means adding
one adapter here — nothing downstream changes.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.guardian.models import NormalizedArticle


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
