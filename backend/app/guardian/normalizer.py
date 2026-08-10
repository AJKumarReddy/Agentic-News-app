"""Convert raw Guardian Content API items into NormalizedArticle records."""

import hashlib
import re
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup

from app.guardian.models import NormalizedArticle

_WHITESPACE_RE = re.compile(r"[ \t]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def clean_html(html: str) -> str:
    """Strip Guardian body HTML down to readable plain text, preserving paragraphs."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for element in soup(["script", "style", "figure", "aside", "iframe"]):
        element.decompose()
    blocks: list[str] = []
    paragraphs = soup.find_all(["p", "h2", "h3", "li", "blockquote"])
    if paragraphs:
        for node in paragraphs:
            text = node.get_text(" ", strip=True)
            if text:
                blocks.append(text)
    else:
        text = soup.get_text(" ", strip=True)
        if text:
            blocks.append(text)
    joined = "\n\n".join(blocks)
    joined = _WHITESPACE_RE.sub(" ", joined)
    return _MULTI_NEWLINE_RE.sub("\n\n", joined).strip()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def normalize_article(item: dict[str, Any]) -> NormalizedArticle:
    """Map a Guardian API result (with show-fields/show-tags) to our model."""
    fields = item.get("fields") or {}
    tags = item.get("tags") or []

    byline = fields.get("byline", "")
    if not byline:
        contributors = [t.get("webTitle", "") for t in tags if t.get("type") == "contributor"]
        byline = ", ".join(c for c in contributors if c)

    keyword_tags = [t.get("id", "") for t in tags if t.get("type") == "keyword" and t.get("id")]

    body_html = fields.get("body", "")
    body_text = fields.get("bodyText") or clean_html(body_html)
    trail_text = clean_html(fields.get("trailText", ""))

    return NormalizedArticle(
        article_id=item.get("id", ""),
        headline=fields.get("headline") or item.get("webTitle", ""),
        section=item.get("sectionName", "") or item.get("sectionId", ""),
        author=byline,
        published_at=_parse_date(item.get("webPublicationDate")),
        url=item.get("webUrl", ""),
        thumbnail=fields.get("thumbnail", ""),
        trail_text=trail_text,
        body_text=body_text,
        tags=keyword_tags,
        production_office=(fields.get("productionOffice") or "").upper(),
        content_hash=content_hash(body_text or trail_text or item.get("webTitle", "")),
    )
