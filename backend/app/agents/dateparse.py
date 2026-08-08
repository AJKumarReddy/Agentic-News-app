"""Deterministic natural-language date range parsing.

The LLM router may also propose ISO dates, but for the well-known phrases
below this parser is authoritative — deterministic behavior beats model
variance for date math.
"""

import re
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


def _replace_word_numbers(text: str) -> str:
    for word, number in _WORD_NUMBERS.items():
        text = re.sub(rf"\b{word}\b", str(number), text)
    return text


def parse_date_range(text: str, today: date | None = None) -> tuple[str, str] | None:
    """Return (from_date, to_date) as ISO strings, or None if no expression found."""
    today = today or date.today()
    lowered = _replace_word_numbers(text.lower())

    def span(start: date, end: date) -> tuple[str, str]:
        return start.isoformat(), end.isoformat()

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
        # Freshness terms without an explicit range → last 7 days
        return span(today - timedelta(days=7), today)
    return None


def detect_freshness(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in FRESHNESS_TERMS)
