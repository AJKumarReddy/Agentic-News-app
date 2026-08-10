"""News source abstraction.

Every provider returns the same NormalizedArticle, so retrieval, chunking,
citations and the UI stay source-agnostic. Adding a publisher means adding
one adapter here — nothing downstream changes.
"""

from abc import ABC, abstractmethod

from app.guardian.models import NormalizedArticle


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

    async def ping(self) -> bool:
        try:
            await self.search(page_size=1)
            return True
        except NewsSourceError:
            return False

    async def aclose(self) -> None:
        return None
