"""Feed ranking: clustering, then scoring.

The thing under test is a judgement, so these assert on *orderings* rather than
on absolute scores — the weights are meant to be tuned, and a test that pins
them to three decimal places would fail on every tune without catching a single
real regression.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.guardian.models import NormalizedArticle
from app.services.ranking import (
    STALE_AFTER_HOURS,
    cluster,
    freshness_score,
    rank,
    source_authority,
)

NOW = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)


def article(headline, *, minutes_ago=10, source="The Guardian", section="Politics", trail=""):
    return NormalizedArticle(
        article_id=f"id/{headline[:24]}/{source}",
        headline=headline,
        section=section,
        url=f"https://example.com/{abs(hash((headline, source)))}",
        source=source,
        trail_text=trail,
        published_at=NOW - timedelta(minutes=minutes_ago),
    )


# ── freshness ────────────────────────────────────────────────────

def test_recency_decays_in_the_right_order():
    """The brief's own ladder: 15min > 2h > 12h > 2day."""
    scores = [freshness_score(h) for h in (0.25, 2, 12, 48)]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] > 0.9
    assert scores[-1] < 0.05


def test_an_undated_article_is_not_treated_as_brand_new():
    """Otherwise every article missing a timestamp leads the feed."""
    undated = article("Something happened")
    undated.published_at = None
    ranked = rank([undated, article("Ordinary council meeting", minutes_ago=5)], now=NOW)
    assert ranked[0].article.headline == "Ordinary council meeting"


# ── recency must not beat consequence ────────────────────────────

def test_a_major_story_outranks_a_fresher_trivial_one():
    """The whole reason this is not `ORDER BY published_at DESC`."""
    ranked = rank(
        [
            article("Parish council approves new bins", minutes_ago=1),
            article(
                "Supreme court ruling strikes down the emergency powers act",
                minutes_ago=90,
                trail="The verdict ends a year of litigation.",
            ),
        ],
        now=NOW,
    )
    assert "Supreme court" in ranked[0].article.headline


def test_but_freshness_still_separates_equals():
    """Two comparable stories: the newer one leads."""
    ranked = rank(
        [
            article("Senate passes the spending bill", minutes_ago=600),
            article("Senate blocks the nominations package", minutes_ago=15),
        ],
        now=NOW,
    )
    assert ranked[0].article.headline.endswith("nominations package")


def test_stale_articles_are_pushed_down_not_merely_faded():
    old = article("Major earthquake strikes the region", minutes_ago=int(STALE_AFTER_HOURS * 60) + 120)
    fresh = article("Routine committee hearing opens", minutes_ago=5)
    ranked = rank([old, fresh], now=NOW)
    assert ranked[0].article.headline == "Routine committee hearing opens"


# ── clustering ───────────────────────────────────────────────────

def test_one_event_across_six_outlets_is_one_card():
    headline = "Federal Reserve announces quarter-point interest rate cut"
    stories = cluster([article(headline, source=s) for s in
                       ("Reuters", "apnews.com", "bbc.com", "cnbc.com", "The Guardian", "nytimes.com")])
    assert len(stories) == 1
    assert stories[0].independent_sources == 6


def test_the_cluster_is_fronted_by_the_strongest_source():
    stories = cluster([
        article("Federal Reserve announces quarter-point rate cut", source="randomblog.example"),
        article("Federal Reserve announces quarter-point rate cut", source="reuters.com"),
    ])
    assert stories[0].article.source == "reuters.com"
    assert len(stories[0].supporting) == 1


def test_unrelated_stories_are_not_merged():
    stories = cluster([
        article("Federal Reserve announces quarter-point rate cut"),
        article("Hurricane makes landfall on the Gulf coast"),
        article("Arsenal beat Coventry in the league opener"),
    ])
    assert len(stories) == 3


def test_syndication_is_not_counted_as_independent_confirmation():
    """Six copies from one outlet is one newsroom's work, not six."""
    stories = cluster([article("Rate cut announced by the central bank", source="cnbc.com")
                       for _ in range(6)])
    assert stories[0].independent_sources == 1


def test_corroboration_lifts_a_story_over_a_lone_report():
    """Several independent newsrooms running the same event is evidence it
    matters — the least gameable signal available here."""
    widely = [article("Central bank raises rates in surprise decision", source=s, minutes_ago=120)
              for s in ("reuters.com", "apnews.com", "bbc.com", "bloomberg.com")]
    alone = [article("Local firm announces quarterly results", minutes_ago=100)]
    ranked = rank(widely + alone, now=NOW)
    assert "Central bank" in ranked[0].article.headline


# ── categories and market impact ─────────────────────────────────

def test_priority_categories_lead_all_else_equal():
    ranked = rank(
        [
            article("Team announces new training ground", section="Sport", minutes_ago=30),
            article("Chancellor sets out the budget timetable", section="Politics", minutes_ago=30),
        ],
        now=NOW,
    )
    assert ranked[0].article.section == "Politics"


def test_market_impact_only_applies_to_business_stories():
    """Fabricating market relevance for a sports story would be a lie the
    ranking tells itself."""
    ranked = rank(
        [
            article("Inflation falls as the Fed signals a rate cut",
                    section="Business", minutes_ago=60, trail="Treasury yields moved."),
            article("Inflation of ticket prices angers supporters",
                    section="Sport", minutes_ago=60),
        ],
        now=NOW,
    )
    assert ranked[0].article.section == "Business"


def test_high_impact_stories_outside_the_big_four_still_surface():
    """The homepage must not collapse into politics/finance/tech/sports."""
    ranked = rank(
        [
            article("Minor cabinet reshuffle expected next month",
                    section="Politics", minutes_ago=30),
            article("Magnitude 7.4 earthquake kills hundreds near the capital",
                    section="World", minutes_ago=30, trail="Rescuers search the rubble."),
        ],
        now=NOW,
    )
    assert "earthquake" in ranked[0].article.headline


# ── authority ────────────────────────────────────────────────────

@pytest.mark.parametrize("name,expected_higher", [("reuters.com", "randomblog.example")])
def test_known_newsrooms_outrank_unknown_ones(name, expected_higher):
    assert source_authority(article("x", source=name)) > source_authority(
        article("x", source=expected_higher)
    )


def test_authority_reads_the_relaying_publisher_not_the_aggregator():
    """Relayed articles carry their real outlet in `source`."""
    assert source_authority(article("x", source="reuters.com")) > 0.9


def test_ranking_an_empty_feed_is_empty_not_an_error():
    assert rank([], now=NOW) == []


# ── where ranking applies ────────────────────────────────────────

async def test_a_bare_browse_is_ranked_but_an_explicit_search_is_not(monkeypatch):
    """Ranking applies exactly where the reader stated no preference.

    Typing keywords, or asking for oldest-first, is an instruction; re-sorting
    that by our idea of importance overrides them. A bare browse is not an
    instruction, and `published_at DESC` is a poor default there.
    """
    from app.services import search_service

    trivial = article("Parish council approves new bins", minutes_ago=1)
    major = article(
        "Supreme court ruling strikes down the emergency powers act",
        minutes_ago=90,
        trail="The verdict ends a year of litigation.",
    )

    class OneSource:
        id = "guardian"
        bulk_efficient = True

        async def search_page(self, **kwargs):
            from app.sources.base import SourceResult

            return SourceResult(articles=[trivial, major], total=2, pages=1)

    monkeypatch.setattr(search_service, "enabled_sources", lambda: [OneSource()])

    browsed = await search_service.search_news(page_size=10)
    assert "Supreme court" in browsed.articles[0].headline, "a browse should be ranked"

    searched = await search_service.search_news(query="bins", page_size=10)
    assert searched.articles[0].headline.startswith("Parish council"), (
        "an explicit search keeps the reader's own ordering"
    )

    oldest = await search_service.search_news(order_by="oldest", page_size=10)
    assert "Supreme court" in oldest.articles[0].headline, (
        "oldest-first is an instruction and must not be re-ranked"
    )


# ── edition preference ───────────────────────────────────────────

def test_the_served_edition_leads_between_comparable_stories():
    """A US audience is not equally served by a Westminster process story and
    a Washington one. `PREFERRED_PRODUCTION_OFFICE` decides which desk that is."""
    us = article("Senate committee advances the spending bill", minutes_ago=30)
    us.production_office = "US"
    uk = article("Commons committee advances the finance bill", minutes_ago=30)
    uk.production_office = "UK"
    ranked = rank([uk, us], now=NOW)
    assert ranked[0].article.production_office == "US"


def test_edition_is_a_nudge_not_a_filter():
    """A major story from any desk still beats a minor local one."""
    minor_us = article("City council reviews parking permits", minutes_ago=20)
    minor_us.production_office = "US"
    major_uk = article(
        "Supreme court ruling strikes down the emergency powers act",
        minutes_ago=45,
        trail="The verdict ends a year of litigation.",
    )
    major_uk.production_office = "UK"
    ranked = rank([minor_us, major_uk], now=NOW)
    assert "Supreme court" in ranked[0].article.headline


def test_sources_without_an_edition_are_not_penalised():
    """Most non-Guardian publishers leave production_office empty; docking them
    for it would demote whole sources for a field they never set."""
    from app.services.ranking import score_story, Story

    blank = article("Central bank holds rates steady", minutes_ago=30)
    blank.production_office = ""
    uk = article("Central bank holds rates steady", minutes_ago=30)
    uk.production_office = "UK"
    assert score_story(Story(article=blank), now=NOW) == score_story(Story(article=uk), now=NOW)
