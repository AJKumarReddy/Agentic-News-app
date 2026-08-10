"""Source registry: which publishers are active, and who owns an article id."""

import logging

from app.core.config import get_settings
from app.sources.base import NewsSource
from app.sources.guardian_source import GuardianSource
from app.sources.nyt import NYTSource

logger = logging.getLogger(__name__)

_sources: dict[str, NewsSource] | None = None


def _build() -> dict[str, NewsSource]:
    return {source.id: source for source in (GuardianSource(), NYTSource())}


def all_sources() -> dict[str, NewsSource]:
    global _sources
    if _sources is None:
        _sources = _build()
    return _sources


def enabled_sources() -> list[NewsSource]:
    """Active publishers, ordered by the ENABLED_SOURCES setting.

    A source with no API key configured is skipped, so the app runs on
    whichever keys are present rather than failing.
    """
    registry = all_sources()
    wanted = [s.strip().lower() for s in get_settings().enabled_sources.split(",") if s.strip()]
    ordered = [registry[name] for name in wanted if name in registry]
    return [source for source in ordered if source.enabled]


def get_source(source_id: str) -> NewsSource | None:
    return all_sources().get(source_id)


def source_for_article(article_id: str) -> NewsSource | None:
    """Which enabled source can fetch this article id."""
    for source in enabled_sources():
        if source.owns(article_id):
            return source
    return None


def source_domains() -> list[str]:
    """Domains covered by our own sources — excluded from web search so
    results never duplicate reporting we already cite directly."""
    return [source.domain for source in all_sources().values() if source.domain]


async def close_all() -> None:
    for source in all_sources().values():
        await source.aclose()
