"""Section vocabulary shared by ingestion, retrieval and browsing.

Two problems live here.

**Spelling.** We ask publishers for a unified slug ("us-news") but they store a
display name: the Guardian keeps `sectionName` ("US news"), the NYT keeps a
desk ("U.S."). Comparing the slug to either matches nothing, so a section
filter silently returned an empty result — a filter that excludes everything
looks exactly like a topic with no coverage. Both sides are reduced to letters
and digits before comparison.

**Breadth.** A section is a filing decision, not a subject. US political
reporting is filed under `us-news`, `politics`, `world` and `commentisfree`
depending on the desk and the day, so pinning a question to the single section
a model guessed throws away most of the coverage. `related_sections` expands a
slug into the sections that genuinely carry the same subject.
"""

import re

#: Sections whose reporting overlaps enough that a question about one is
#: normally a question about all of them. Deliberately conservative: these are
#: subject neighbours, not a taxonomy.
SECTION_GROUPS: dict[str, list[str]] = {
    "us-news": ["us-news", "politics", "world", "commentisfree"],
    "politics": ["politics", "us-news", "world", "commentisfree"],
    "world": ["world", "politics", "us-news"],
    "business": ["business", "money", "technology"],
    "money": ["money", "business"],
    "technology": ["technology", "business", "science"],
    "science": ["science", "environment", "technology"],
    "environment": ["environment", "science", "world"],
    "society": ["society", "us-news", "world"],
    "media": ["media", "business", "technology"],
    "culture": ["culture", "film", "music", "books"],
    "film": ["film", "culture"],
    "music": ["music", "culture"],
    "books": ["books", "culture"],
    "sport": ["sport"],
    "football": ["football", "sport"],
    "travel": ["travel"],
    "food": ["food", "lifestyle"],
    "fashion": ["fashion", "lifestyle"],
    "commentisfree": ["commentisfree", "politics", "us-news"],
}


#: Display names that do not reduce to their slug. Most do — "US news" meets
#: "us-news", "Technology" meets "technology" — but a few desks are published
#: under a different word entirely, and those match nothing without help.
SECTION_ALIASES: dict[str, list[str]] = {
    "commentisfree": ["opinion", "comment"],
    "us-news": ["usa", "unitedstates"],
    "sport": ["sports"],
    "football": ["soccer"],
    "society": ["health"],
    "money": ["personalfinance"],
    "culture": ["arts", "artsandentertainment"],
    "film": ["movies"],
    "environment": ["climate"],
}


def canonical_section(section: str) -> str:
    """Letters and digits only, lowercased: "US news" and "us-news" both
    become "usnews", and "U.S." becomes "us"."""
    return re.sub(r"[^a-z0-9]+", "", section.lower())


def section_match_values(section: str) -> list[str]:
    """Canonical spellings a stored section may take for this slug.

    "us-news" has to match the Guardian's "US news" (canonical "usnews") *and*
    the NYT's "U.S." (canonical "us"), so the bare stem is included alongside
    the "news" suffixed form.
    """
    base = canonical_section(section)
    if not base:
        return []
    stem = base[: -len("news")] if base.endswith("news") and len(base) > len("news") else base
    values = [base, stem, f"{stem}news"]
    values.extend(SECTION_ALIASES.get(section.strip().lower(), []))
    return list(dict.fromkeys(values))


def related_sections(section: str) -> list[str]:
    """The slug plus the sections that carry the same subject."""
    if not section:
        return []
    return SECTION_GROUPS.get(section.strip().lower(), [section.strip().lower()])


def section_variants(section: str) -> list[str]:
    """Stored `section` spellings a slug should match, canonicalised.

    Used wherever a section is compared against the column, so the caller must
    canonicalise the column too — see `app.rag.vector_store._section_column`.
    """
    return section_match_values(section)
