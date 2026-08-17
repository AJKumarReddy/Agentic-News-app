"""Section matching and breadth.

Two separate causes of "the index is too narrow":

  * the slug we filter with ("us-news") never equalled the display name a
    publisher stores ("US news", "U.S."), so a section-filtered retrieval
    matched nothing — indistinguishable from a subject nobody covered;
  * even matched exactly, one section is not one subject. US political
    reporting is filed across us-news, politics, world and commentisfree.
"""

import pytest

from app.agents.graph import _build_filters
from app.sources.sections import (
    SECTION_GROUPS,
    canonical_section,
    related_sections,
    section_match_values,
)
from app.tasks.ingest_recent import DEFAULT_SECTIONS, rotating_sections


# ── the slug has to meet the stored spelling ──────────────────────

@pytest.mark.parametrize(
    "slug,stored",
    [
        ("us-news", "US news"),   # Guardian sectionName
        ("us-news", "U.S."),      # NYT desk
        ("us-news", "Us"),
        ("world", "World news"),
        ("world", "World"),
        ("technology", "Technology"),
        # a few desks publish under a different word entirely
        ("commentisfree", "Opinion"),
        ("sport", "Sports"),
        ("environment", "Climate"),
        ("film", "Movies"),
    ],
)
def test_stored_spellings_match_the_slug(slug, stored):
    assert canonical_section(stored) in section_match_values(slug)


def test_punctuation_and_case_are_irrelevant():
    assert canonical_section("U.S.") == "us"
    assert canonical_section("US news") == "usnews"
    assert canonical_section("us-news") == "usnews"


def test_distinct_sections_never_collide():
    for a in ("world", "business", "technology", "sport"):
        for b in ("world", "business", "technology", "sport"):
            if a != b:
                assert not set(section_match_values(a)) & set(section_match_values(b)), (a, b)


# ── one section is not one subject ────────────────────────────────

def test_us_politics_reaches_every_desk_that_carries_it():
    for slug in ("us-news", "politics"):
        related = related_sections(slug)
        assert "us-news" in related
        assert "politics" in related
        assert "world" in related


def test_the_requested_section_always_leads():
    for slug, group in SECTION_GROUPS.items():
        assert group[0] == slug, slug


def test_an_unknown_section_is_left_alone():
    assert related_sections("weather") == ["weather"]
    assert related_sections("") == []


def test_retrieval_filters_widen_the_section():
    filters = _build_filters({"section": "us-news"})
    assert filters.sections[0] == "us-news"
    assert "politics" in filters.sections


def test_unrelated_sections_are_not_pulled_in():
    filters = _build_filters({"section": "sport"})
    assert filters.sections == ["sport"]


# ── the index has to contain those desks in the first place ───────

def test_every_grouped_section_is_actually_ingested():
    """Widening retrieval to a desk we never pull is a filter over nothing."""
    ingested = set(DEFAULT_SECTIONS)
    for slug in ("us-news", "politics", "world", "commentisfree"):
        assert slug in ingested, slug


def test_rotation_covers_every_section():
    seen = set()
    for tick in range(len(DEFAULT_SECTIONS) * 2):
        seen.update(rotating_sections(tick, 1))
    assert seen == set(DEFAULT_SECTIONS)
