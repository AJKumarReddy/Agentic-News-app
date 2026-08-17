from datetime import date

from app.agents.dateparse import detect_freshness, mentions_written_date, parse_date_range

TODAY = date(2026, 8, 8)  # a Saturday


def span(text: str):
    parsed = parse_date_range(text, TODAY)
    return parsed.span if parsed else None


def test_today():
    assert span("climate stories today") == ("2026-08-08", "2026-08-08")


def test_yesterday():
    assert span("what happened yesterday") == ("2026-08-07", "2026-08-07")


def test_this_week_is_a_rolling_seven_days():
    """Not the calendar week: anchored to Monday it collapsed to a single day
    every Monday, so "US politics this week" returned that morning alone."""
    assert span("US politics this week") == ("2026-08-01", "2026-08-08")


def test_this_week_is_never_degenerate():
    monday = date(2026, 8, 17)
    start, end = parse_date_range("US politics this week", monday).span
    assert start != end
    assert (date.fromisoformat(end) - date.fromisoformat(start)).days == 7


def test_last_week_full_span():
    assert span("last week") == ("2026-07-27", "2026-08-02")


def test_this_month_is_a_rolling_thirty_days():
    # a calendar month is a one-day window on the 1st, for the same reason
    assert span("NVIDIA this month") == ("2026-07-09", "2026-08-08")


def test_this_month_is_never_degenerate():
    first = date(2026, 8, 1)
    start, end = parse_date_range("NVIDIA this month", first).span
    assert start != end


def test_last_month():
    assert span("last month") == ("2026-07-01", "2026-07-31")


def test_last_7_days():
    assert span("AI stories in the last 7 days") == ("2026-08-01", "2026-08-08")


def test_past_three_months_word_number():
    assert span("over the past three months") == ("2026-05-08", "2026-08-08")


def test_this_year():
    assert span("this year") == ("2026-01-01", "2026-08-08")


def test_latest_defaults_to_seven_days():
    assert span("latest OpenAI news") == ("2026-08-01", "2026-08-08")


def test_no_expression_returns_none():
    assert parse_date_range("tell me about the history of the BBC", TODAY) is None


def test_freshness_detection():
    assert detect_freshness("latest AI developments")
    assert detect_freshness("breaking news on the election")
    assert not detect_freshness("history of the internet in 1995")


# ── stated vs inferred ranges ─────────────────────────────────────
# Only an inferred window may be widened when it finds nothing.

def test_a_named_period_is_explicit():
    for text in ("last week", "this month", "in the last 7 days", "yesterday", "this year"):
        assert parse_date_range(text, TODAY).explicit is True, text


def test_a_freshness_word_is_an_inference():
    for text in ("latest OpenAI news", "recent coverage", "breaking stories"):
        assert parse_date_range(text, TODAY).explicit is False, text


def test_written_dates_are_detected():
    for text in (
        "articles from March",
        "coverage in 2024",
        "between 5 and 20 January",
        "anything on 2026-03-01",
        "stories from 12/03/2025",
    ):
        assert mentions_written_date(text), text


def test_bare_topics_carry_no_written_date():
    for text in ("latest AI news", "what did the Guardian say about the strike", "tell me more"):
        assert not mentions_written_date(text), text
