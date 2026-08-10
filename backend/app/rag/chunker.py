"""Recursive, paragraph-aware chunking.

Targets 600–1000 tokens per chunk with ~15% overlap. Splits on paragraph
boundaries first, then sentences when a single paragraph is too large.
Each unit's token count is computed exactly once — tokenization dominates
ingestion CPU cost.
"""

import re
from dataclasses import dataclass

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


def _split_oversized(paragraph: str, max_tokens: int) -> list[tuple[str, int]]:
    """Break a paragraph larger than max_tokens into (sentence-group, tokens) pieces."""
    sentences = [s.strip() for s in _SENTENCE_RE.split(paragraph) if s.strip()] or [paragraph]
    pieces: list[tuple[str, int]] = []
    current: list[str] = []
    current_tokens = 0
    for sentence in sentences:
        sentence_tokens = count_tokens(sentence)
        if current and current_tokens + sentence_tokens > max_tokens:
            pieces.append((" ".join(current), current_tokens))
            current, current_tokens = [], 0
        current.append(sentence)
        current_tokens += sentence_tokens
    if current:
        pieces.append((" ".join(current), current_tokens))
    return pieces


def chunk_text(
    text: str,
    target_tokens: int = 800,
    overlap_tokens: int = 120,
) -> list[TextChunk]:
    text = text.strip()
    if not text:
        return []
    if count_tokens(text) <= target_tokens:
        return [TextChunk(text=text, chunk_index=0)]

    # Atomic units as (text, token_count): paragraphs, splitting oversized ones
    units: list[tuple[str, int]] = []
    for paragraph in (p.strip() for p in text.split("\n\n")):
        if not paragraph:
            continue
        tokens = count_tokens(paragraph)
        if tokens > target_tokens:
            units.extend(_split_oversized(paragraph, target_tokens))
        else:
            units.append((paragraph, tokens))

    chunks: list[TextChunk] = []
    current: list[tuple[str, int]] = []
    current_tokens = 0
    for unit in units:
        if current and current_tokens + unit[1] > target_tokens:
            chunks.append(TextChunk("\n\n".join(u[0] for u in current), len(chunks)))
            # Overlap: carry trailing units into the next chunk
            overlap: list[tuple[str, int]] = []
            overlap_count = 0
            for prev in reversed(current):
                if overlap_count + prev[1] > overlap_tokens:
                    break
                overlap.insert(0, prev)
                overlap_count += prev[1]
            current = overlap
            current_tokens = overlap_count
        current.append(unit)
        current_tokens += unit[1]
    if current:
        chunks.append(TextChunk("\n\n".join(u[0] for u in current), len(chunks)))
    return chunks
