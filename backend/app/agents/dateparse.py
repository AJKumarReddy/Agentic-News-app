"""Deterministic natural-language date range parsing.

The understanding step may also propose ISO dates, but for the well-known
phrases below this parser is authoritative — deterministic behavior beats
model variance for date math.

A range carries whether the user *stated* it or we *inferred* it. That
distinction decides how strictly retrieval enforces it: "articles from March"
is a constraint and must never be quietly widened, while the 7-day window
behind a bare "latest" is our own guess and may be relaxed when it finds
nothing. Conflating the two is what made date filtering look unreliable.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

FRESHNESS_TERMS = {
    "latest", "recent", "recently", "today", "yesterday", "this week",
    "this month", "current", "currently", "breaking", "new", "now",
    "past week", "past month", "this year", "just announced",
}

_LAST_N_DAYS = re.compile(r"\b(?:last|past)\s+(\d+)\s+days?\b")
_LAST_N_WEEKS = re.compile(r"\b(?:last|past)\s+(\d+)\s+weeks?\b")
_LAST_N_MONTHS = re.compile(r"\b(?:last|past)\s+(\d+)\s+months?\b")
_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12,
}


_MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|november|december"
    "|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec"
)

# A date the user actually wrote down, in any of the forms a model might then
# turn into ISO. Used to tell a stated range from an inferred one when the
# range came from the model rather than from the patterns below.
_WRITTEN_DATE = re.compile(
    rf"\b(?:{_MONTHS})\b|\b(?:19|20)\d{{2}}\b|\b\d{{4}}-\d{{2}}-\d{{2}}\b"
    r"|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|\bq[1-4]\b|\bbetween\b.{0,30}\band\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DateRange:
    from_date: str
    to_date: str
    # True when the user stated the range; False when we inferred it from a
    # freshness word. Only inferred ranges may be widened by retrieval.
    explicit: bool = True

    @property
    def span(self) -> tuple[str, str]:
        return self.from_date, self.to_date


def _replace_word_numbers(text: str) -> str:
    for word, number in _WORD_NUMBERS.items():
        text = re.sub(rf"\b{word}\b", str(number), text)
    return text


def mentions_written_date(text: str) -> bool:
    """Did the user write a date themselves (month, year, ISO, 12/03)?

    The model fills `from_date`/`to_date` for phrasings this module doesn't
    parse ("between 5 and 20 January"). Those are stated ranges too, and this
    is how we know not to widen them.
    """
    return bool(_WRITTEN_DATE.search(text))


def parse_date_range(text: str, today: date | None = None) -> DateRange | None:
    """Resolve a natural-language date expression, or None if there isn't one."""
    today = today or date.today()
    lowered = _replace_word_numbers(text.lower())

    def span(start: date, end: date, explicit: bool = True) -> DateRange:
        return DateRange(start.isoformat(), end.isoformat(), explicit)

    if re.search(r"\btoday\b", lowered):
        return span(today, today)
    if re.search(r"\byesterday\b", lowered):
        return span(today - timedelta(days=1), today - timedelta(days=1))
    if re.search(r"\bthis week\b", lowered):
        return span(today - timedelta(days=today.weekday()), today)
    if re.search(r"\blast week\b", lowered):
        start = today - timedelta(days=today.weekday() + 7)
        return span(start, start + timedelta(days=6))
    if re.search(r"\bthis month\b", lowered):
        return span(today.replace(day=1), today)
    if re.search(r"\blast month\b", lowered):
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        return span(last_prev.replace(day=1), last_prev)
    if re.search(r"\bthis year\b", lowered):
        return span(today.replace(month=1, day=1), today)
    if re.search(r"\blast year\b", lowered):
        return span(
            today.replace(year=today.year - 1, month=1, day=1),
            today.replace(year=today.year - 1, month=12, day=31),
        )
    match = _LAST_N_DAYS.search(lowered)
    if match:
        return span(today - timedelta(days=int(match.group(1))), today)
    match = _LAST_N_WEEKS.search(lowered)
    if match:
        return span(today - timedelta(weeks=int(match.group(1))), today)
    match = _LAST_N_MONTHS.search(lowered)
    if match:
        return span(today - relativedelta(months=int(match.group(1))), today)
    if re.search(r"\b(latest|recent|recently|breaking|current)\b", lowered):
        # Freshness terms carry no range — 7 days is our inference, not the
        # user's instruction, so retrieval is free to widen it.
        return span(today - timedelta(days=7), today, explicit=False)
    return None


def detect_freshness(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in FRESHNESS_TERMS)
