"""The canonical category layer.

What matters here is that one canonical category maps to one request per
provider. The app used to browse by Guardian slug, so "finance", "money",
"economy" and "business" were four calls returning heavily overlapping
stories — against providers that meter requests, on a free tier capped at 100
a day.
"""

from app.sources.categories import (
    CATEGORIES,
    CATEGORIES_BY_ID,
    PRIORITY_IDS,
    default_weights,
    provider_sections,
    resolve,
)


def test_the_default_feed_shape_adds_up():
    total = sum(default_weights().values())
    assert abs(total - 1.0) < 1e-9, f"weights should describe a whole feed, got {total}"


def test_priority_categories_are_the_ones_worth_waiting_for():
    # these three are fetched before the first render; sports and the
    # high-impact slot load behind it
    assert PRIORITY_IDS == ("politics", "business", "technology")


def test_money_and_business_are_one_category_not_two():
    """The saving this layer exists for: one canonical id, one request."""
    assert resolve("how are the markets doing?") == "business"
    assert resolve("what is inflation doing") == "business"
    assert resolve("federal reserve decision") == "business"
    assert resolve("tell me about the economy") == "business"
    # and they all reach the same provider call
    assert provider_sections("business", "thenewsapi") == ("business",)


def test_free_text_reaches_the_right_category():
    assert resolve("what's happening in AI?") == "technology"
    assert resolve("who won the election") == "politics"
    assert resolve("championship final result") == "sports"
    assert resolve("the earthquake damage") == "world"


def test_short_aliases_do_not_match_inside_words():
    """"ai" must not match "said", "fed" must not match "defended" — the
    padding in resolve() is the whole reason those aliases are safe."""
    assert resolve("he said nothing") != "technology"
    assert resolve("she defended the ruling") != "business"


def test_unknown_text_means_the_default_feed_not_an_empty_one():
    assert resolve("") is None
    assert resolve("zxcvbnm qwerty") is None


def test_every_category_is_reachable_from_every_configured_provider():
    for category in CATEGORIES:
        for source in ("guardian", "nyt", "thenewsapi"):
            assert provider_sections(category.id, source), (
                f"{category.id} has no {source} mapping, so browsing it would "
                "silently drop that publisher from the feed"
            )


def test_an_unknown_provider_or_category_is_empty_not_an_error():
    # the caller reads empty as "ask without a section filter"; a provider
    # missing one desk must not remove it from the feed
    assert provider_sections("politics", "nosuchsource") == ()
    assert provider_sections("nosuchcategory", "guardian") == ()


def test_the_high_impact_slot_covers_more_than_the_four_headline_beats():
    """The homepage must not collapse into politics/finance/tech/sports."""
    world = CATEGORIES_BY_ID["world"]
    for subject in ("science", "health", "climate", "disaster", "court"):
        assert subject in world.aliases, subject
