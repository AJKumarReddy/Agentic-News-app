from app.guardian.normalizer import clean_html, content_hash, normalize_article

SAMPLE_ITEM = {
    "id": "technology/2026/aug/07/openai-announcement",
    "webTitle": "OpenAI announces new model",
    "webUrl": "https://www.theguardian.com/technology/2026/aug/07/openai-announcement",
    "webPublicationDate": "2026-08-07T10:30:00Z",
    "sectionName": "Technology",
    "fields": {
        "headline": "OpenAI announces new model",
        "trailText": "The <strong>latest</strong> release raises questions",
        "body": "<p>First paragraph about the model.</p><figure>ignored</figure><p>Second paragraph with <a href='#'>a link</a>.</p><script>evil()</script>",
        "thumbnail": "https://media.guim.co.uk/thumb.jpg",
        "byline": "Jane Reporter",
    },
    "tags": [
        {"id": "technology/openai", "type": "keyword", "webTitle": "OpenAI"},
        {"id": "profile/jane-reporter", "type": "contributor", "webTitle": "Jane Reporter"},
    ],
}


def test_clean_html_strips_markup_and_scripts():
    text = clean_html(SAMPLE_ITEM["fields"]["body"])
    assert "First paragraph about the model." in text
    assert "Second paragraph with a link ." in text or "Second paragraph with a link." in text
    assert "evil" not in text
    assert "ignored" not in text
    assert "<p>" not in text


def test_normalize_article_fields():
    article = normalize_article(SAMPLE_ITEM)
    assert article.article_id == "technology/2026/aug/07/openai-announcement"
    assert article.headline == "OpenAI announces new model"
    assert article.section == "Technology"
    assert article.author == "Jane Reporter"
    assert article.url.startswith("https://www.theguardian.com/")
    assert article.tags == ["technology/openai"]
    assert article.published_at is not None
    assert article.published_at.year == 2026
    assert article.source == "The Guardian"


def test_content_hash_stable_and_sensitive():
    a = normalize_article(SAMPLE_ITEM)
    b = normalize_article(SAMPLE_ITEM)
    assert a.content_hash == b.content_hash
    changed = dict(SAMPLE_ITEM)
    changed["fields"] = {**SAMPLE_ITEM["fields"], "body": "<p>Different body entirely.</p>"}
    assert normalize_article(changed).content_hash != a.content_hash


def test_missing_byline_falls_back_to_contributor_tags():
    item = dict(SAMPLE_ITEM)
    item["fields"] = {k: v for k, v in SAMPLE_ITEM["fields"].items() if k != "byline"}
    article = normalize_article(item)
    assert article.author == "Jane Reporter"
