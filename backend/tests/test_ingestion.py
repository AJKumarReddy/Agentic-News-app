from datetime import datetime, timezone

from app.database.models import Article
from app.guardian.models import NormalizedArticle
from app.rag.ingestion import needs_indexing

MODEL = "text-embedding-3-small"


def make_incoming(content_hash: str = "hash-a") -> NormalizedArticle:
    return NormalizedArticle(
        article_id="technology/2026/aug/07/story",
        headline="Story",
        url="https://www.theguardian.com/technology/2026/aug/07/story",
        body_text="Body text.",
        content_hash=content_hash,
    )


def make_existing(content_hash: str = "hash-a", indexed: bool = True) -> Article:
    article = Article(article_id="technology/2026/aug/07/story", content_hash=content_hash)
    if indexed:
        article.first_indexed_at = datetime.now(timezone.utc)
        article.embedding_model = MODEL
    return article


def test_unseen_article_needs_indexing():
    assert needs_indexing(None, make_incoming(), MODEL) is True


def test_seen_but_never_indexed_needs_indexing():
    assert needs_indexing(make_existing(indexed=False), make_incoming(), MODEL) is True


def test_identical_content_is_skipped():
    assert needs_indexing(make_existing("hash-a"), make_incoming("hash-a"), MODEL) is False


def test_changed_content_reindexed():
    assert needs_indexing(make_existing("hash-a"), make_incoming("hash-b"), MODEL) is True


def test_embedding_model_change_triggers_reindex():
    existing = make_existing("hash-a")
    existing.embedding_model = "some-old-model"
    assert needs_indexing(existing, make_incoming("hash-a"), MODEL) is True
