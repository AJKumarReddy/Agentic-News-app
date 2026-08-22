"""Canonical news categories, and the one place their weights live.

The app previously browsed by Guardian section slug — eighteen of them, then
ten — and each publisher mapped that slug its own way. That had two costs. It
spent a request per slug, so "finance", "money", "economy" and "business" were
four calls to say one thing; and it left the homepage's shape implicit, decided
by whichever slugs happened to be listed rather than by what a reader wants
first.

So categories are declared here, once: what each covers, what each provider
calls it, and how much of the default feed it should claim. Everything that
ranks, fetches or renders a category reads from this module rather than
carrying its own copy — `NEWS_RANKING_WEIGHTS` and `CATEGORY_PRIORITY` are not
scattered constants but fields on these records.

`weight` is a starting share of the feed, not a quota. A ranking pass is
expected to override it when a story's own significance earns the space — a
war, a rate decision, an election result. See `default_weights()`.
"""

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Category:
    """One canonical category and how each provider spells it."""

    id: str
    label: str
    #: Share of the default homepage feed, before any ranking adjustment.
    #: These sum to 1.0 across the set below.
    weight: float
    #: Fetched in the first wave. The rest load behind the first render.
    priority: bool
    #: Guardian section ids. Several map to one category on purpose: the
    #: Guardian files money and business separately, and a reader asking for
    #: "business" means both.
    guardian: tuple[str, ...] = ()
    #: NYT desk names (Article Search) — its own vocabulary again.
    nyt: tuple[str, ...] = ()
    #: TheNewsAPI categories, from its fixed set of ten.
    thenewsapi: tuple[str, ...] = ()
    #: Words that should route a free-text request here, beyond the label.
    #: Used to resolve "what's happening in AI?" to technology.
    aliases: tuple[str, ...] = field(default_factory=tuple)


#: The canonical set. Ordered by default prominence, which is also the order
#: the homepage renders them in before ranking reshuffles anything.
CATEGORIES: tuple[Category, ...] = (
    Category(
        id="politics",
        label="Politics & Government",
        weight=0.32,
        priority=True,
        guardian=("politics", "us-news", "commentisfree"),
        nyt=("Politics", "U.S.", "Washington"),
        thenewsapi=("politics",),
        aliases=(
            "government", "election", "elections", "policy", "public policy",
            "white house", "congress", "senate", "parliament", "geopolitics",
            "administration", "vote", "campaign",
        ),
    ),
    Category(
        id="business",
        label="Business, Finance & Economy",
        weight=0.22,
        priority=True,
        # One category, one request per provider. These four used to be four
        # separate calls returning heavily overlapping stories.
        guardian=("business", "money"),
        nyt=("Business Day", "Economy"),
        thenewsapi=("business",),
        aliases=(
            "finance", "money", "economy", "economic", "markets", "market",
            "banking", "bank", "inflation", "jobs", "employment",
            "interest rates", "federal reserve", "fed", "stocks", "trade",
            "earnings", "merger", "acquisition", "treasury", "currency",
            "commodities", "nasdaq", "s&p", "dow",
        ),
    ),
    Category(
        id="technology",
        label="Technology",
        weight=0.18,
        priority=True,
        guardian=("technology",),
        nyt=("Technology",),
        thenewsapi=("tech",),
        aliases=(
            "ai", "artificial intelligence", "software", "semiconductor",
            "semiconductors", "chips", "cybersecurity", "security breach",
            "big tech", "startup", "startups", "app", "platform", "data",
            "machine learning", "robotics",
        ),
    ),
    Category(
        id="sports",
        label="Sports",
        weight=0.13,
        priority=False,
        guardian=("sport", "football"),
        nyt=("Sports",),
        thenewsapi=("sports",),
        aliases=(
            "sport", "football", "soccer", "basketball", "cricket", "tennis",
            "olympics", "championship", "final", "league", "nba", "nfl",
        ),
    ),
    Category(
        id="world",
        label="High-Impact Other",
        weight=0.15,
        priority=False,
        # Deliberately broad. This is the slot that keeps the homepage from
        # collapsing into politics-finance-tech-sports: a discovery, an
        # earthquake, a court ruling, a public-health event.
        guardian=("world", "science", "environment", "society", "culture"),
        nyt=("World", "Science", "Climate", "Health"),
        thenewsapi=("general", "science", "health"),
        aliases=(
            "world", "science", "health", "climate", "environment", "disaster",
            "earthquake", "hurricane", "weather", "crime", "court", "ruling",
            "space", "discovery", "outbreak", "pandemic", "culture",
            "entertainment",
        ),
    ),
)

CATEGORIES_BY_ID: dict[str, Category] = {c.id: c for c in CATEGORIES}

#: Categories fetched before the first render. The rest follow behind it, so
#: the homepage is useful before every provider has answered.
PRIORITY_IDS: tuple[str, ...] = tuple(c.id for c in CATEGORIES if c.priority)


def default_weights() -> dict[str, float]:
    """Starting share of the feed per category.

    A starting point, not a quota — a ranking pass is expected to move a
    genuinely major story above its category's allocation. Kept as a function
    rather than a constant so a future personalisation layer can compose:

        effective = default_weights() + user_interest + query_intent + breaking
    """
    return {c.id: c.weight for c in CATEGORIES}


def provider_sections(category_id: str, source_id: str) -> tuple[str, ...]:
    """What one provider calls this category.

    Empty when the category is unknown or the provider has no equivalent, which
    the caller should read as "ask without a section filter" rather than as an
    error — a provider missing one desk should not remove it from the feed.
    """
    category = CATEGORIES_BY_ID.get(category_id)
    if category is None:
        return ()
    return {
        "guardian": category.guardian,
        "nyt": category.nyt,
        "thenewsapi": category.thenewsapi,
    }.get(source_id, ())


#: Everything that is not a letter or digit becomes a space, so "AI?" and
#: "(AI)" and "AI," all reduce to the same token. Applied to the text and to
#: the alias alike, which is what lets the padded comparison below be exact.
_NON_WORD = re.compile(r"[^a-z0-9]+")


def _normalise(text: str) -> str:
    return f" {_NON_WORD.sub(' ', text.casefold()).strip()} "


def resolve(text: str) -> str | None:
    """The canonical category a free-text request is asking for, if any.

    Lets "what's happening in AI?" reach technology and "how are markets
    doing?" reach business, without the caller knowing any provider's
    vocabulary. Returns None when nothing matches, which means the default
    priority feed rather than an empty result.
    """
    if not text:
        return None
    haystack = _normalise(text)
    for category in CATEGORIES:
        for needle in (category.id, category.label, *category.aliases):
            # both sides normalised, and the needle padded, so "ai" does not
            # match "said" and "fed" does not match "defended" — the short
            # aliases are the whole reason this is not a plain substring test
            if _normalise(needle).strip() and _normalise(needle) in haystack:
                return category.id
    return None


def ingest_sections() -> list[str]:
    """Every Guardian desk the canonical categories cover, weightiest first.

    Every desk, not one per category, and that is a correctness requirement
    rather than thoroughness: retrieval widens a slug into its subject
    neighbours (`app/sources/sections.py`), so a question about `us-news` also
    looks under `politics`, `world` and `commentisfree`. A desk that is never
    ingested makes that widening a filter over an empty set — the query looks
    broader and finds less.

    Ordering by category weight is what makes the budget count. The rotation
    walks this list, so the categories the feed leads with come round first
    after a restart and are never the ones starved when a cycle is cut short.
    """
    ordered = sorted(CATEGORIES, key=lambda c: c.weight, reverse=True)
    seen: list[str] = []
    for category in ordered:
        for slug in category.guardian:
            if slug not in seen:
                seen.append(slug)
    return seen
