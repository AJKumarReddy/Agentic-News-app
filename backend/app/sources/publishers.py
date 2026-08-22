"""Publisher display names.

TheNewsAPI relays hundreds of newsrooms and reports each one by its domain
("foxnews.com"), which is what `Article.source` carries - citing the newsroom
rather than the aggregator that relayed it. That is right for attribution and
wrong for reading, and the evidence labels handed to the model come back to
the user almost verbatim: label a chunk "foxnews.com" and the answer says
"according to foxnews.com".

So the domain stays in the data, and this maps it to a name at the point the
label is written. An allowlist cannot cover an aggregator's whole tail, so an
unlisted domain falls back to a tidied form of the domain itself - "Sfgate" is
imperfect, but it reads as a name, which "sfgate.com" never does.

Deliberately kept in step with `frontend/src/utils/publisher.ts`, which does
the same job for the UI. The two run over different data - the model's
evidence labels here, stored articles there - so both need the mapping.
"""

import re

#: Curated names for outlets we see often. Spelled as the newsroom spells
#: itself, not as the domain does.
PUBLISHERS: dict[str, str] = {
    "theguardian.com": "The Guardian",
    "nytimes.com": "The New York Times",
    "washingtonpost.com": "The Washington Post",
    "wsj.com": "The Wall Street Journal",
    "ft.com": "Financial Times",
    "reuters.com": "Reuters",
    "apnews.com": "AP News",
    "bbc.com": "BBC News",
    "bbc.co.uk": "BBC News",
    "bloomberg.com": "Bloomberg",
    "cnbc.com": "CNBC",
    "cnn.com": "CNN",
    "foxnews.com": "FOX News",
    "foxbusiness.com": "FOX Business",
    "nypost.com": "NY Post",
    "cbsnews.com": "CBS News",
    "nbcnews.com": "NBC News",
    "abcnews.go.com": "ABC News",
    "npr.org": "NPR",
    "politico.com": "Politico",
    "axios.com": "Axios",
    "theverge.com": "The Verge",
    "arstechnica.com": "Ars Technica",
    "techcrunch.com": "TechCrunch",
    "engadget.com": "Engadget",
    "wired.com": "WIRED",
    "usatoday.com": "USA Today",
    "latimes.com": "Los Angeles Times",
    "nbcnewyork.com": "NBC New York",
    "thehill.com": "The Hill",
    "newsweek.com": "Newsweek",
    "time.com": "TIME",
    "forbes.com": "Forbes",
    "businessinsider.com": "Business Insider",
    "economist.com": "The Economist",
    "independent.co.uk": "The Independent",
    "telegraph.co.uk": "The Telegraph",
    "thetimes.co.uk": "The Times",
    "dailymail.co.uk": "Daily Mail",
    "mirror.co.uk": "The Mirror",
    "standard.co.uk": "Evening Standard",
    "sky.com": "Sky News",
    "news.sky.com": "Sky News",
    "aljazeera.com": "Al Jazeera",
    "euronews.com": "Euronews",
    "dw.com": "DW",
    "france24.com": "France 24",
    "scmp.com": "South China Morning Post",
    "straitstimes.com": "The Straits Times",
    "theatlantic.com": "The Atlantic",
    "newyorker.com": "The New Yorker",
    "vox.com": "Vox",
    "slate.com": "Slate",
    "salon.com": "Salon",
    "thedailybeast.com": "The Daily Beast",
    "huffpost.com": "HuffPost",
    "buzzfeednews.com": "BuzzFeed News",
    "yahoo.com": "Yahoo News",
    "news.yahoo.com": "Yahoo News",
    "msn.com": "MSN",
    "marketwatch.com": "MarketWatch",
    "barrons.com": "Barron's",
    "fortune.com": "Fortune",
    "espn.com": "ESPN",
    "skysports.com": "Sky Sports",
    "variety.com": "Variety",
    "hollywoodreporter.com": "The Hollywood Reporter",
    "deadline.com": "Deadline",
    "nature.com": "Nature",
    "sciencedaily.com": "ScienceDaily",
    "newscientist.com": "New Scientist",
    "gizmodo.com": "Gizmodo",
    "zdnet.com": "ZDNET",
    "venturebeat.com": "VentureBeat",
    "theregister.com": "The Register",
    "thenextweb.com": "The Next Web",
}

#: Suffix labels dropped when tidying an unlisted domain. Not a full public
#: suffix list - just enough to leave the brand behind.
SUFFIXES: frozenset[str] = frozenset({
    "com", "org", "net", "co", "uk", "us", "io", "gov", "edu", "int", "info", "biz",
    "tv", "me", "news", "go", "ca", "au", "nz", "ie", "in", "de", "fr", "es",
    "it", "nl", "se", "no", "dk", "fi", "jp", "cn", "br", "za", "ru",
})

#: Domains look like `a.b`; display names contain spaces or lack a TLD tail.
_DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$", re.IGNORECASE)


def _normalize_host(value: str) -> str:
    host = value.strip().lower()
    host = re.sub(r"^https?://", "", host)
    host = re.sub(r"^www\.", "", host)
    host = host.split("/", 1)[0]
    return host.rstrip(".")


def _prettify(host: str) -> str:
    """Last resort for a domain we have no curated name for."""
    labels = [label for label in host.split(".") if label]
    while len(labels) > 1 and labels[-1] in SUFFIXES:
        labels.pop()
    brand = labels[-1] if labels else host
    return " ".join(word.capitalize() for word in brand.split("-") if word)


def publisher_name(raw: str | None) -> str:
    """A publisher name fit to show a reader.

    Values that are already names - "The Guardian" - pass through untouched.
    """
    if not raw:
        return ""
    trimmed = raw.strip()
    if not trimmed:
        return ""

    host = _normalize_host(trimmed)
    curated = PUBLISHERS.get(host)
    if curated:
        return curated

    # Only rewrite things that are actually domains; leave real names alone.
    if not _DOMAIN_RE.match(host):
        return trimmed

    return _prettify(host)
