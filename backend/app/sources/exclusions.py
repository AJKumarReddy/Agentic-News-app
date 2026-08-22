"""What must never reach the feed: puzzles, and anything paid for.

Both categories are things a newspaper publishes that are not news. They arrive
mixed in with reporting from every provider — the Guardian files crosswords
under `crosswords` and `lifeandstyle`, aggregators relay sponsored posts with
the rest — and they are filtered here, during normalisation, so they are gone
*before* ranking. Filtering later would be too late in a way that matters: a
promoted post that survives into the ranker can win a priority slot on
freshness alone, and the reader sees an advert where the top story should be.

Two rules, in order of trust:

1. **Structured signals first.** A section, a category, or a URL path is
   something the publisher asserted; a headline is prose. `sponsored` in a
   section field is a fact, `"Sponsored by"` in a headline is a guess.
2. **Text only as a backstop**, and only on the headline and section — never
   on the body, where an ordinary article about the advertising industry would
   trip every one of these words.

That second point is the whole reason this is not one big regex over
everything: "Meta's advertising revenue fell" is news about advertising, and a
naive keyword filter removes it.
"""

import re

#: Non-news interactive content. Matched against section, category and URL
#: path, where these appear as their own filing, and against the headline,
#: where they are conventionally named outright ("Crossword No 29,412").
PUZZLE_TERMS = (
    "crossword",
    "cryptic",
    "quick crossword",
    "puzzle",
    "sudoku",
    "wordsearch",
    "word search",
    "quiz",
    "trivia",
    "brain teaser",
    "brainteaser",
    "daily challenge",
)

#: Paid placement. Publishers and aggregators label this in metadata far more
#: reliably than in the headline, which is why the structured check leads.
PROMOTIONAL_TERMS = (
    "sponsored",
    "advertisement",
    "advertorial",
    "paid content",
    "paid post",
    "paid-content",
    "paid-post",
    "promoted",
    "promotion",
    "brand content",
    "branded content",
    "partner content",
    "partner zone",
    "affiliate",
    "shopping",
    "deals",
)

#: URL path fragments. A provider that labels nothing still routes this content
#: to its own part of the site.
_PATH_MARKERS = (
    "/crosswords/",
    "/crossword/",
    "/puzzles/",
    "/puzzle/",
    "/games/",
    "/sudoku/",
    "/quiz/",
    "/sponsored/",
    "/advertorial/",
    "/paid-content/",
    "/partner-zone/",
    "/affiliate/",
)

#: Guardian sections that are entirely non-news, matched exactly rather than by
#: substring so `crosswords` is caught but `news` is not.
_EXCLUDED_SECTIONS = {
    "crosswords",
    "games",
    "puzzles",
    "thefilter",  # the Guardian's affiliate shopping vertical
}

_WORD = re.compile(r"[^a-z0-9]+")


def _tokens(text: str) -> str:
    return f" {_WORD.sub(' ', (text or '').casefold()).strip()} "


def _mentions(text: str, terms: tuple[str, ...]) -> bool:
    haystack = _tokens(text)
    return any(f" {_WORD.sub(' ', term).strip()} " in haystack for term in terms)


#: A puzzle *instance* is titled like one — "Quick crossword No 17,204",
#: "Sudoku 3,801 hard", "Weekend quiz: ..." — carrying a serial number or
#: labelling itself before a colon. An article *about* puzzles is prose:
#: "How the cryptic crossword survived a century". The bare term appears in
#: both, so the term alone cannot be the test.
_HAS_NUMBER = re.compile(r"\d")


def _is_puzzle_headline(headline: str) -> bool:
    if not headline or not _mentions(headline, PUZZLE_TERMS):
        return False
    if _HAS_NUMBER.search(headline):
        return True
    # a label before a colon is the publisher naming the format, not a sentence
    label, separator, _ = headline.partition(":")
    return bool(separator) and _mentions(label, PUZZLE_TERMS)


def exclusion_reason(
    *,
    headline: str = "",
    section: str = "",
    url: str = "",
    tags: tuple[str, ...] | list[str] = (),
) -> str:
    """Why this item is not news, or "" if it is.

    Returns a reason rather than a bool so the caller can log what it dropped —
    a filter that silently eats articles is impossible to tune, and the first
    question when a real story goes missing is which rule took it.
    """
    lowered_section = _WORD.sub("", (section or "").casefold())
    if lowered_section in _EXCLUDED_SECTIONS:
        return f"section:{lowered_section}"

    path = (url or "").casefold()
    for marker in _PATH_MARKERS:
        if marker in path:
            return f"url:{marker.strip('/')}"

    # Structured fields carry the publisher's own assertion, so they are
    # trusted for both rule sets.
    for field_name, value in (("section", section), ("tags", " ".join(tags or ()))):
        if _mentions(value, PROMOTIONAL_TERMS):
            return f"promotional:{field_name}"
        if _mentions(value, PUZZLE_TERMS):
            return f"puzzle:{field_name}"

    # Headline last, and only for puzzles, which name themselves. Promotional
    # wording is deliberately *not* matched here: "Meta's advertising revenue
    # fell" and "the sponsored-content backlash" are news about advertising,
    # and dropping them would be a worse failure than keeping the rare advert
    # that carried no metadata at all.
    if _is_puzzle_headline(headline):
        return "puzzle:headline"

    return ""


def is_excluded(**kwargs) -> bool:
    return bool(exclusion_reason(**kwargs))
