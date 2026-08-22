"""What leads the feed, and why.

Sorting by `published_at DESC` is the obvious thing and the wrong thing: it
puts a five-minute-old county-council item above an hour-old rate decision.
What a reader wants is a balance of *importance*, *relevance* and *freshness*,
which is what this module computes.

Every weight lives here. Nothing downstream carries its own magic number, so
the feed's shape can be tuned — or later composed with user preferences and
query intent — by editing one dataclass rather than hunting constants.

Two passes, in this order:

1. **Cluster.** Six outlets covering one rate decision is one story, not six
   cards. The cluster collapses to a representative article and the rest
   become supporting sources — and the fact that several *independent*
   newsrooms ran it is itself evidence the story matters, so it raises the
   score rather than repeating the card.

2. **Score.** Category weight, time decay, significance, authority and
   confirmation combine into one number.

The ordering matters: scoring before clustering would let six near-identical
copies each earn a top slot on their own merits and crowd everything else out.
"""

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.guardian.models import NormalizedArticle
from app.core.config import get_settings
from app.sources.categories import CATEGORIES, CATEGORIES_BY_ID


@dataclass(frozen=True)
class RankingWeights:
    """How much each signal is worth. The one place these live."""

    category_priority: float = 1.0
    freshness: float = 1.2
    significance: float = 0.9
    source_authority: float = 0.4
    #: Independent corroboration. Weighted heavily because it is the least
    #: gameable signal here — a single outlet can write any headline it likes,
    #: but it cannot make five others cover the same event.
    cross_source: float = 0.8
    market_impact: float = 0.5
    #: Reporting from the edition this deployment serves. A nudge, not a
    #: filter — a major story from any desk still outranks a minor local one,
    #: but between comparable stories the reader's own region wins.
    edition: float = 0.45
    #: Applied to a story already represented by a stronger member of its
    #: cluster, for the rare case one survives into the ranked list.
    duplicate_penalty: float = 0.6
    stale_penalty: float = 0.7


NEWS_RANKING_WEIGHTS = RankingWeights()

#: Hours for the freshness score to halve. Six keeps a morning story alive
#: through the working day while a two-day-old one is effectively gone:
#: 15min→0.97, 2h→0.79, 12h→0.25, 48h→0.004.
FRESHNESS_HALF_LIFE_HOURS = 6.0

#: Past this, an article is actively penalised rather than merely faded. A
#: rolling feed that still leads with last week is worse than a shorter one.
STALE_AFTER_HOURS = 72.0

#: Editorial standing, 0–1. Deliberately coarse: this is a nudge, not a
#: verdict on journalism, and the point is to prefer an original report over a
#: rewrite of it. Unlisted publishers get `DEFAULT_AUTHORITY`.
SOURCE_AUTHORITY: dict[str, float] = {
    "theguardian.com": 0.9,
    "nytimes.com": 0.95,
    "reuters.com": 0.95,
    "apnews.com": 0.95,
    "bbc.co.uk": 0.9,
    "bbc.com": 0.9,
    "bloomberg.com": 0.9,
    "wsj.com": 0.9,
    "ft.com": 0.9,
    "washingtonpost.com": 0.85,
    "cnbc.com": 0.8,
    "cbsnews.com": 0.75,
    "nbcnews.com": 0.75,
    "abcnews.go.com": 0.75,
    "npr.org": 0.8,
    "politico.com": 0.75,
    "axios.com": 0.7,
    "theverge.com": 0.7,
    "arstechnica.com": 0.7,
}
DEFAULT_AUTHORITY = 0.5

#: Words that mark a story as consequential rather than routine. Matched on the
#: headline and standfirst only — the body of almost any article mentions at
#: least one of these in passing.
SIGNIFICANCE_TERMS: tuple[str, ...] = (
    "war", "invasion", "ceasefire", "airstrike", "killed", "dead", "death toll",
    "earthquake", "hurricane", "wildfire", "flood", "disaster", "evacuated",
    "outbreak", "pandemic", "emergency",
    "resigns", "resignation", "impeach", "indicted", "convicted", "verdict",
    "supreme court", "ruling", "sanctions", "treaty", "summit",
    "election", "wins", "defeat", "coup", "referendum",
    "crash", "collapse", "bankruptcy", "bailout", "recession",
    "recall", "explosion", "attack", "shooting", "hostage",
    "breakthrough", "discovery", "landing", "launch",
)

#: Finance signals. Kept separate from significance because they earn their own
#: configurable weight — a rate decision matters differently from an earthquake.
MARKET_TERMS: tuple[str, ...] = (
    "federal reserve", "fed", "interest rate", "rate cut", "rate rise",
    "inflation", "cpi", "jobs report", "unemployment", "payrolls",
    "s&p", "nasdaq", "dow", "ftse", "treasury", "yields", "bond",
    "earnings", "profit warning", "merger", "acquisition", "takeover",
    "ipo", "tariff", "trade deal", "opec", "oil price", "central bank",
    "recession", "gdp", "stimulus", "default",
)

_WORD = re.compile(r"[^a-z0-9]+")
#: Words too common to say anything about whether two headlines are the same
#: story. Without this, "The" and "of" alone push unrelated pairs over the
#: similarity threshold.
_STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the "
    "to was were will with after over into their his her they this these than "
    "but not new says say said report reports amid ahead".split()
)


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD.sub(" ", (text or "").casefold()).split() if w not in _STOPWORDS and len(w) > 2}


def _padded(text: str) -> str:
    return f" {_WORD.sub(' ', (text or '').casefold()).strip()} "


def _mentions(text: str, terms: tuple[str, ...]) -> int:
    haystack = _padded(text)
    return sum(1 for term in terms if f" {_WORD.sub(' ', term).strip()} " in haystack)


def _age_hours(article: NormalizedArticle, now: datetime) -> float:
    published = article.published_at
    if published is None:
        # Undated is not fresh. Treating it as "now" would let every article
        # without a timestamp lead the feed.
        return STALE_AFTER_HOURS
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return max(0.0, (now - published).total_seconds() / 3600.0)


def freshness_score(age_hours: float) -> float:
    """Exponential decay, 1.0 at publication."""
    return math.pow(0.5, age_hours / FRESHNESS_HALF_LIFE_HOURS)


def source_authority(article: NormalizedArticle) -> float:
    """0–1 for the newsroom that reported it.

    Relayed articles carry their publisher in `source` (see the TheNewsAPI
    adapter), so this reads the actual outlet rather than the pipe.
    """
    name = (article.source or "").casefold().strip()
    if name in SOURCE_AUTHORITY:
        return SOURCE_AUTHORITY[name]
    for domain, score in SOURCE_AUTHORITY.items():
        if domain in name:
            return score
    return DEFAULT_AUTHORITY


def category_of(article: NormalizedArticle) -> str | None:
    """Which canonical category this article belongs to, by its section."""
    section = _padded(article.section)
    for category in CATEGORIES:
        for slug in (*category.guardian, *category.nyt, *category.thenewsapi):
            if f" {_WORD.sub(' ', slug).strip()} " in section:
                return category.id
    return None


@dataclass
class Story:
    """One event: the article that represents it, plus who else ran it."""

    article: NormalizedArticle
    #: Other outlets' coverage of the same event. Kept rather than discarded so
    #: the UI can cite them as corroboration instead of showing six near
    #: identical cards.
    supporting: list[NormalizedArticle] = field(default_factory=list)
    score: float = 0.0

    @property
    def independent_sources(self) -> int:
        """Distinct outlets covering this, counting the representative.

        Distinct *outlets*, not articles: a wire story republished under three
        mastheads of one group is one newsroom's work, and rewarding it as
        three would be exactly the syndication trap.
        """
        names = {(self.article.source or "").casefold()}
        names.update((a.source or "").casefold() for a in self.supporting)
        return len(names - {""}) or 1


def cluster(articles: list[NormalizedArticle], *, threshold: float = 0.5) -> list[Story]:
    """Group articles describing the same event.

    Jaccard overlap of significant headline words. Deliberately simple: it runs
    on every feed render, and an embedding-based clusterer would put a model
    call on the request path for a job that headline overlap does well enough.

    The representative is the highest-authority member, so the cluster is
    fronted by the outlet most likely to have reported it first-hand rather
    than by whichever copy happened to sort first.
    """
    stories: list[Story] = []
    signatures: list[set[str]] = []

    for article in articles:
        tokens = _tokens(article.headline)
        placed = False
        for index, signature in enumerate(signatures):
            union = tokens | signature
            if not union:
                continue
            overlap = len(tokens & signature) / len(union)
            if overlap >= threshold:
                story = stories[index]
                # keep the strongest source at the front of the cluster
                if source_authority(article) > source_authority(story.article):
                    story.supporting.append(story.article)
                    story.article = article
                else:
                    story.supporting.append(article)
                signatures[index] = signature | tokens
                placed = True
                break
        if not placed:
            stories.append(Story(article=article))
            signatures.append(tokens)
    return stories


def score_story(
    story: Story,
    *,
    now: datetime,
    weights: RankingWeights = NEWS_RANKING_WEIGHTS,
    category_weights: dict[str, float] | None = None,
) -> float:
    """The combined relevance score for one story."""
    article = story.article
    text = f"{article.headline} {article.trail_text}"

    category = category_of(article)
    weights_by_category = category_weights or {c.id: c.weight for c in CATEGORIES}
    # An article we cannot categorise is not thereby unimportant — it scores
    # the mean rather than zero, so an unmapped desk is not silently buried.
    priority = weights_by_category.get(category or "", sum(weights_by_category.values()) / len(weights_by_category))

    age = _age_hours(article, now)
    fresh = freshness_score(age)

    # Diminishing returns: the difference between one and three significance
    # words is real, between eight and ten is noise.
    significance = min(1.0, _mentions(text, SIGNIFICANCE_TERMS) / 3.0)
    market = min(1.0, _mentions(text, MARKET_TERMS) / 3.0) if category == "business" else 0.0

    # Corroboration saturates too — the third independent outlet says much more
    # than the ninth.
    confirmation = min(1.0, math.log1p(story.independent_sources - 1) / math.log(4))

    # The Guardian files UK and Australian editions alongside US reporting, and
    # for a US audience a Westminster process story is not the equal of a
    # Washington one. `production_office` carries the desk; an article without
    # one is neither rewarded nor punished, since most non-Guardian sources
    # leave it empty and penalising them would demote whole publishers.
    preferred = get_settings().preferred_production_office.strip().upper()
    desk = (article.production_office or "").strip().upper()
    edition = 1.0 if preferred and desk == preferred else 0.0

    score = (
        weights.category_priority * priority
        + weights.freshness * fresh
        + weights.significance * significance
        + weights.source_authority * source_authority(article)
        + weights.cross_source * confirmation
        + weights.market_impact * market
        + weights.edition * edition
    )
    if age > STALE_AFTER_HOURS:
        score -= weights.stale_penalty
    return score


def rank(
    articles: list[NormalizedArticle],
    *,
    now: datetime | None = None,
    weights: RankingWeights = NEWS_RANKING_WEIGHTS,
    category_weights: dict[str, float] | None = None,
) -> list[Story]:
    """Cluster, score, and order. The feed, in the order a reader should see it.

    Clustering first is what stops six copies of one story each earning a top
    slot and crowding the rest of the day off the page.
    """
    now = now or datetime.now(timezone.utc)
    stories = cluster(articles)
    for story in stories:
        story.score = score_story(
            story, now=now, weights=weights, category_weights=category_weights
        )
    stories.sort(key=lambda s: s.score, reverse=True)
    return stories


def category_label(category_id: str | None) -> str:
    category = CATEGORIES_BY_ID.get(category_id or "")
    return category.label if category else "News"
