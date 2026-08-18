"""Transforms over answer prose, shared by everything that re-reads an answer.

The citation marker lives here rather than inside the agent graph because two
unrelated consumers need one definition of what a citation looks like: history
replay strips them so a number from an earlier turn cannot be reused in a turn
whose source list means something else, and speech strips them because a
listener hears "bracket one" as a defect rather than as a source.
"""

import re

#: A bracketed source number as it appears in a synthesised answer, together
#: with any whitespace before it. `Markdown.tsx` splits on exactly this shape
#: to render the clickable badges, so the markers are literal in stored text.
CITATION_MARKER = re.compile(r"\s*\[\d+\]")

# Markdown that carries meaning to the eye and none to the ear. Order matters
# below: images before links (an image is a link with a bang), and fences
# before inline code, or the fence's own backticks are eaten first.
_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_HEADING_LINE = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$")
_BLOCKQUOTE = re.compile(r"^\s{0,3}>\s?", re.MULTILINE)
_LIST_BULLET_LINE = re.compile(r"^\s{0,8}(?:[-*+]|\d+[.)])\s+(.*)$")
_RULE = re.compile(r"^\s{0,3}(?:[-*_]\s*){3,}$", re.MULTILINE)
#: Characters that already close a clause, so no full stop is needed.
_TERMINAL = ".!?:;,"
# A GFM table row: a line fenced by pipes. Dropped whole — there is no reading
# of a pipe-delimited grid that beats silence, and the prose around a table
# carries the same facts in sentences.
_TABLE_ROW = re.compile(r"^\s{0,3}\|.*\|\s*$", re.MULTILINE)
_BOLD_ITALIC = re.compile(r"\*{1,3}(\S(?:.*?\S)?)\*{1,3}", re.DOTALL)
# Underscore emphasis only when it is not inside a word, so snake_case
# identifiers quoted in an answer survive intact.
_UNDERSCORE_EMPHASIS = re.compile(r"(?<!\w)_{1,3}(\S(?:.*?\S)?)_{1,3}(?!\w)", re.DOTALL)
_TRAILING_SPACE = re.compile(r"[ \t]+$", re.MULTILINE)
_BLANK_RUN = re.compile(r"\n{3,}")


def _close_clause(text: str) -> str:
    """A full stop where a line has no terminal punctuation of its own."""
    text = text.rstrip()
    if not text:
        return text
    return text if text[-1] in _TERMINAL else f"{text}."


def _flatten_blocks(text: str) -> str:
    """Headings and list items become sentences.

    Removing the marker alone is not enough. A bullet and a heading each carry
    a pause to the eye that nothing replaces in audio, so a stripped list runs
    into one long breathless clause and a heading collides with the sentence
    beneath it. A full stop restores the beat the punctuation never had to.
    """
    lines: list[str] = []
    for line in text.split("\n"):
        heading = _HEADING_LINE.match(line)
        if heading:
            lines.append(_close_clause(heading.group(1)))
            continue
        item = _LIST_BULLET_LINE.match(line)
        if item:
            lines.append(_close_clause(item.group(1)))
            continue
        lines.append(line)
    return "\n".join(lines)


def speakable_text(markdown: str) -> str:
    """Answer prose reduced to something worth listening to.

    Returns "" when nothing speakable survives — an answer that was entirely a
    table, say. Callers must read that as "do not synthesise" rather than
    sending an empty string to the speech API, which costs a request and
    returns a fraction of a second of silence.
    """
    if not markdown:
        return ""

    text = CITATION_MARKER.sub("", markdown)
    text = _CODE_FENCE.sub(" ", text)
    text = _TABLE_ROW.sub("", text)
    # rules before list flattening, or "- - -" reads as a bullet
    text = _RULE.sub("", text)
    text = _IMAGE.sub(r"\1", text)
    text = _LINK.sub(r"\1", text)
    text = _flatten_blocks(text)
    text = _BLOCKQUOTE.sub("", text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _BOLD_ITALIC.sub(r"\1", text)
    text = _UNDERSCORE_EMPHASIS.sub(r"\1", text)
    text = _TRAILING_SPACE.sub("", text)
    text = _BLANK_RUN.sub("\n\n", text)
    return text.strip()


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def split_for_speech(text: str, limit: int) -> list[str]:
    """Segments under `limit` characters, split between sentences.

    The speech API caps input length, and synthesis runs at max_tokens=1800,
    so a long answer can exceed it. Splitting mid-sentence is audible at the
    join; splitting between them is not. A single sentence longer than the
    limit is rare enough that a hard split on the last space is fine.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    segments: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(text):
        if not sentence:
            continue
        while len(sentence) > limit:
            cut = sentence.rfind(" ", 0, limit)
            if cut <= 0:
                cut = limit
            if current:
                segments.append(current)
                current = ""
            segments.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if not current:
            current = sentence
        elif len(current) + 1 + len(sentence) <= limit:
            current = f"{current} {sentence}"
        else:
            segments.append(current)
            current = sentence
    if current:
        segments.append(current)
    return [s for s in segments if s]
