import pytest

from app.services import search_service
from app.sources.base import SourceResult


@pytest.fixture(autouse=True)
def offline_store(monkeypatch):
    """Keep `search_news` off the real database.

    Searching now writes results back to the article store and reads from it
    when a publisher is unreachable. Neither belongs in a unit test: the write
    would leave fixture rows in the developer's local database, and the read
    would make assertions depend on whatever happens to be in it.

    Tests that exercise the fallback override `_from_store` themselves.
    """

    async def no_write(articles):
        return None

    async def empty_store(source, **kwargs):
        return SourceResult()

    monkeypatch.setattr(search_service, "_remember", no_write)
    monkeypatch.setattr(search_service, "_from_store", empty_store)
