"""Puzzles and paid placement must never reach the feed.

The order matters as much as the rules: this runs during normalisation, before
ranking, because a promoted post that survives into the ranker can win a
priority slot on freshness alone.

Half these tests are the negative case. A filter that removes crosswords is
easy; one that removes crosswords *without* removing "Meta's advertising
revenue fell" is the actual requirement, and keyword matching over everything
fails it.
"""

from app.sources.exclusions import exclusion_reason, is_excluded


def test_a_crossword_filed_as_one_is_excluded():
    assert is_excluded(headline="Quick crossword No 17,204", section="Crosswords")


def test_puzzle_sections_go_by_exact_name():
    assert is_excluded(section="crosswords")
    assert is_excluded(section="Games")
    assert is_excluded(section="Puzzles")
    # substring matching here would take "news" with it
    assert not is_excluded(section="News")
    assert not is_excluded(section="US news")


def test_the_url_catches_what_the_metadata_missed():
    assert is_excluded(url="https://www.theguardian.com/crosswords/cryptic/29412")
    assert is_excluded(url="https://example.com/sponsored/best-laptops-2026")
    assert is_excluded(url="https://example.com/partner-zone/something")


def test_sponsored_metadata_is_excluded():
    assert is_excluded(headline="The best running shoes", section="Sponsored content")
    assert is_excluded(headline="A guide to savings", tags=["paid-content"])
    assert is_excluded(headline="Ten gadgets", tags=["affiliate", "technology"])


def test_a_quiz_names_itself_in_the_headline():
    assert is_excluded(headline="Weekend quiz: how closely did you follow the news?")
    assert is_excluded(headline="Sudoku 3,801 hard")


def test_news_about_advertising_is_still_news():
    """The failure that matters. These all contain promotional vocabulary and
    are all ordinary reporting; a keyword filter over headlines removes them."""
    for headline in (
        "Meta's advertising revenue fell 4% in the quarter",
        "Regulators open inquiry into sponsored political posts",
        "The advertorial backlash reshaping newsroom economics",
        "Supermarket promotion ruled misleading by watchdog",
        "Affiliate marketing industry faces new disclosure rules",
    ):
        assert not is_excluded(headline=headline, section="Business"), headline


def test_news_about_games_and_puzzles_survives_when_properly_filed():
    """A report *about* the crossword is news; the crossword is not."""
    assert not is_excluded(
        headline="How the cryptic crossword survived a century",
        section="Culture",
        url="https://www.theguardian.com/culture/2026/aug/21/cryptic-history",
    )


def test_ordinary_articles_are_untouched():
    for section in ("World news", "Politics", "Business", "Technology", "Sport"):
        assert not is_excluded(
            headline="Senate advances the spending bill",
            section=section,
            url="https://example.com/politics/2026/aug/21/senate-bill",
        )


def test_the_reason_names_the_rule_that_fired():
    """A filter that eats articles silently cannot be tuned — the first
    question when a real story goes missing is which rule took it."""
    assert exclusion_reason(section="crosswords").startswith("section:")
    assert exclusion_reason(url="https://x.com/sponsored/y").startswith("url:")
    assert exclusion_reason(tags=["paid-content"]).startswith("promotional:")
    assert exclusion_reason(headline="Sudoku 3,801").startswith("puzzle:")
    assert exclusion_reason(headline="Senate votes", section="Politics") == ""
