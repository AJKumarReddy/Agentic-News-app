"""Recursive, paragraph-aware chunking.

Targets 600–1000 tokens per chunk with ~15% overlap. Splits on paragraph
boundaries first, then sentences when a single paragraph is too large.
Every chunk carries full article metadata for filtering and citations.
"""

import re
from dataclasses import dataclass, field
from typing import Any

try:
    import tiktoken

    _ENCODER = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        return len(_ENCODER.encode(text))

except Exception:  # pragma: no cover - tiktoken unavailable

    def count_tokens(text: str) -> int:
        return max(1, len(text) // 4)


_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z“\"'])")


@dataclass
class TextChunk:
    text: str
    chunk_index: int
    metadata: dict[str, Any] = field(default_factory=dict)


def _split_sentences(paragraph: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_RE.split(paragraph) if s.strip()]


def _split_oversized(paragraph: str, max_tokens: int) -> list[str]:
    """Break a paragraph larger than max_tokens into sentence groups."""
    sentences = _split_sentences(paragraph) or [paragraph]
    pieces: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for sentence in sentences:
        sentence_tokens = count_tokens(sentence)
        if current and current_tokens + sentence_tokens > max_tokens:
            pieces.append(" ".join(current))
            current, current_tokens = [], 0
        current.append(sentence)
        current_tokens += sentence_tokens
    if current:
        pieces.append(" ".join(current))
    return pieces


def chunk_text(
    text: str,
    metadata: dict[str, Any] | None = None,
    target_tokens: int = 800,
    overlap_tokens: int = 120,
) -> list[TextChunk]:
    metadata = metadata or {}
    text = text.strip()
    if not text:
        return []
    if count_tokens(text) <= target_tokens:
        return [TextChunk(text=text, chunk_index=0, metadata=dict(metadata))]

    # Build atomic units: paragraphs, splitting any paragraph over target size
    units: list[str] = []
    for paragraph in (p.strip() for p in text.split("\n\n")):
        if not paragraph:
            continue
        if count_tokens(paragraph) > target_tokens:
            units.extend(_split_oversized(paragraph, target_tokens))
        else:
            units.append(paragraph)

    chunks: list[TextChunk] = []
    current: list[str] = []
    current_tokens = 0
    for unit in units:
        unit_tokens = count_tokens(unit)
        if current and current_tokens + unit_tokens > target_tokens:
            chunks.append(TextChunk("\n\n".join(current), len(chunks), dict(metadata)))
            # Overlap: carry trailing units into the next chunk
            overlap: list[str] = []
            overlap_count = 0
            for prev in reversed(current):
                prev_tokens = count_tokens(prev)
                if overlap_count + prev_tokens > overlap_tokens:
                    break
                overlap.insert(0, prev)
                overlap_count += prev_tokens
            current = overlap
            current_tokens = overlap_count
        current.append(unit)
        current_tokens += unit_tokens
    if current:
        chunks.append(TextChunk("\n\n".join(current), len(chunks), dict(metadata)))
    return chunks
