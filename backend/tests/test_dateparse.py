from datetime import date

from app.agents.dateparse import detect_freshness, parse_date_range

TODAY = date(2026, 8, 8)  # a Saturday


def test_today():
    assert parse_date_range("climate stories today", TODAY) == ("2026-08-08", "2026-08-08")


def test_yesterday():
    assert parse_date_range("what happened yesterday", TODAY) == ("2026-08-07", "2026-08-07")


def test_this_week_starts_monday():
    assert parse_date_range("US politics this week", TODAY) == ("2026-08-03", "2026-08-08")


def test_last_week_full_span():
    assert parse_date_range("last week", TODAY) == ("2026-07-27", "2026-08-02")


def test_this_month():
    assert parse_date_range("NVIDIA this month", TODAY) == ("2026-08-01", "2026-08-08")


def test_last_month():
    assert parse_date_range("last month", TODAY) == ("2026-07-01", "2026-07-31")


def test_last_7_days():
    assert parse_date_range("AI stories in the last 7 days", TODAY) == ("2026-08-01", "2026-08-08")


def test_past_three_months_word_number():
    assert parse_date_range("over the past three months", TODAY) == ("2026-05-08", "2026-08-08")


def test_this_year():
    assert parse_date_range("this year", TODAY) == ("2026-01-01", "2026-08-08")


def test_latest_defaults_to_seven_days():
    assert parse_date_range("latest OpenAI news", TODAY) == ("2026-08-01", "2026-08-08")


def test_no_expression_returns_none():
    assert parse_date_range("tell me about the history of the BBC", TODAY) is None


def test_freshness_detection():
    assert detect_freshness("latest AI developments")
    assert detect_freshness("breaking news on the election")
    assert not detect_freshness("history of the internet in 1995")
