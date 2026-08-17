"""Guardian adapter over the existing Content API client."""

from app.guardian.client import GuardianAPIError, get_guardian_client
from app.guardian.models import NormalizedArticle
from app.sources.base import NewsSource, NewsSourceError, SourceResult


class GuardianSource(NewsSource):
    id = "guardian"
    name = "The Guardian"
    domain = "theguardian.com"

    def __init__(self, client=None):
        self._client = client or get_guardian_client()

    @property
    def enabled(self) -> bool:
        return bool(self._client.api_key)

    def owns(self, article_id: str) -> bool:
        # Guardian ids are path-like ("technology/2026/aug/07/story") and never
        # carry a scheme, which is what distinguishes them from every other
        # publisher's. Testing only for the "nyt://" prefix made this a
        # catch-all that would claim any source added later, so the id would
        # route here and then fail to resolve.
        return "://" not in article_id

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
        try:
            result = await self._client.search(
                query=query,
                from_date=from_date,
                to_date=to_date,
                section=section,
                order_by=order_by,
                page=page,
                page_size=page_size,
            )
        except GuardianAPIError as exc:
            raise NewsSourceError(str(exc), exc.status_code) from exc
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
        try:
            result = await self._client.search(
                query=query,
                from_date=from_date,
                to_date=to_date,
                section=section,
                order_by=order_by,
                page=page,
                page_size=page_size,
            )
        except GuardianAPIError as exc:
            raise NewsSourceError(str(exc), exc.status_code) from exc
        return SourceResult(articles=result.articles, total=result.total, pages=result.pages)

    async def get_article(self, article_id: str) -> NormalizedArticle | None:
        try:
            return await self._client.get_article(article_id)
        except GuardianAPIError:
            return None

    async def ping(self) -> bool:
        return await self._client.ping()

    async def aclose(self) -> None:
        await self._client.aclose()
