from datetime import datetime, timezone

from pydantic import BaseModel, Field


class GuardianTag(BaseModel):
    id: str
    type: str = ""
    web_title: str = ""


class NormalizedArticle(BaseModel):
    """Canonical article structure used across the whole application.

    article_id is the Guardian content ID (e.g. "technology/2026/aug/07/...")
    and acts as the primary unique identifier everywhere.
    """

    article_id: str
    headline: str
    section: str = ""
    author: str = ""
    published_at: datetime | None = None
    url: str
    thumbnail: str = ""
    trail_text: str = ""
    body_text: str = ""
    tags: list[str] = Field(default_factory=list)
    source: str = "The Guardian"
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    content_hash: str = ""


class GuardianSearchResult(BaseModel):
    total: int = 0
    page: int = 1
    pages: int = 1
    page_size: int = 20
    articles: list[NormalizedArticle] = Field(default_factory=list)
