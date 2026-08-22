/** Publisher display names.
 *
 *  TheNewsAPI relays hundreds of newsrooms and reports each one by its domain
 *  ("foxnews.com"), which is what `Article.source` carries — citing the
 *  newsroom rather than the aggregator that relayed it. That is right for
 *  attribution and wrong for reading: a byline strip reading "nypost.com ·
 *  Politics" looks like a URL someone forgot to format.
 *
 *  So the domain stays in the data and is mapped to a name at render time.
 *  An allowlist cannot cover an aggregator's whole tail, so unlisted domains
 *  fall back to a tidied form of the domain itself — "Sfgate" is imperfect but
 *  it reads as a name, which "sfgate.com" never does.
 */

/** Curated names for outlets we see often. Spelled as the newsroom spells
 *  itself, not as the domain does. */
const PUBLISHERS: Record<string, string> = {
  'theguardian.com': 'The Guardian',
  'nytimes.com': 'The New York Times',
  'washingtonpost.com': 'The Washington Post',
  'wsj.com': 'The Wall Street Journal',
  'ft.com': 'Financial Times',
  'reuters.com': 'Reuters',
  'apnews.com': 'AP News',
  'bbc.com': 'BBC News',
  'bbc.co.uk': 'BBC News',
  'bloomberg.com': 'Bloomberg',
  'cnbc.com': 'CNBC',
  'cnn.com': 'CNN',
  'foxnews.com': 'FOX News',
  'foxbusiness.com': 'FOX Business',
  'nypost.com': 'NY Post',
  'cbsnews.com': 'CBS News',
  'nbcnews.com': 'NBC News',
  'abcnews.go.com': 'ABC News',
  'npr.org': 'NPR',
  'politico.com': 'Politico',
  'axios.com': 'Axios',
  'theverge.com': 'The Verge',
  'arstechnica.com': 'Ars Technica',
  'techcrunch.com': 'TechCrunch',
  'engadget.com': 'Engadget',
  'wired.com': 'WIRED',
  'usatoday.com': 'USA Today',
  'latimes.com': 'Los Angeles Times',
  'nbcnewyork.com': 'NBC New York',
  'thehill.com': 'The Hill',
  'newsweek.com': 'Newsweek',
  'time.com': 'TIME',
  'forbes.com': 'Forbes',
  'businessinsider.com': 'Business Insider',
  'economist.com': 'The Economist',
  'independent.co.uk': 'The Independent',
  'telegraph.co.uk': 'The Telegraph',
  'thetimes.co.uk': 'The Times',
  'dailymail.co.uk': 'Daily Mail',
  'mirror.co.uk': 'The Mirror',
  'standard.co.uk': 'Evening Standard',
  'sky.com': 'Sky News',
  'news.sky.com': 'Sky News',
  'aljazeera.com': 'Al Jazeera',
  'euronews.com': 'Euronews',
  'dw.com': 'DW',
  'france24.com': 'France 24',
  'scmp.com': 'South China Morning Post',
  'straitstimes.com': 'The Straits Times',
  'theatlantic.com': 'The Atlantic',
  'newyorker.com': 'The New Yorker',
  'vox.com': 'Vox',
  'slate.com': 'Slate',
  'salon.com': 'Salon',
  'thedailybeast.com': 'The Daily Beast',
  'huffpost.com': 'HuffPost',
  'buzzfeednews.com': 'BuzzFeed News',
  'yahoo.com': 'Yahoo News',
  'news.yahoo.com': 'Yahoo News',
  'msn.com': 'MSN',
  'marketwatch.com': 'MarketWatch',
  'barrons.com': "Barron's",
  'fortune.com': 'Fortune',
  'espn.com': 'ESPN',
  'skysports.com': 'Sky Sports',
  'variety.com': 'Variety',
  'hollywoodreporter.com': 'The Hollywood Reporter',
  'deadline.com': 'Deadline',
  'nature.com': 'Nature',
  'sciencedaily.com': 'ScienceDaily',
  'newscientist.com': 'New Scientist',
  'gizmodo.com': 'Gizmodo',
  'zdnet.com': 'ZDNET',
  'venturebeat.com': 'VentureBeat',
  'theregister.com': 'The Register',
  'thenextweb.com': 'The Next Web',
};

/** Suffix labels dropped when tidying an unlisted domain. Not a full public
 *  suffix list — just enough to leave the brand behind. */
const SUFFIXES = new Set([
  'com', 'org', 'net', 'co', 'uk', 'us', 'io', 'gov', 'edu', 'int', 'info',
  'biz', 'tv', 'me', 'news', 'go', 'ca', 'au', 'nz', 'ie', 'in', 'de', 'fr',
  'es', 'it', 'nl', 'se', 'no', 'dk', 'fi', 'jp', 'cn', 'br', 'za', 'ru',
]);

/** Domains look like `a.b`; display names contain spaces or lack a TLD tail. */
function looksLikeDomain(value: string): boolean {
  return /^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$/i.test(value);
}

function normalizeHost(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\//, '')
    .replace(/^www\./, '')
    .replace(/\/.*$/, '')
    .replace(/\.$/, '');
}

/** Last resort for a domain we have no curated name for. */
function prettify(host: string): string {
  const labels = host.split('.').filter(Boolean);
  while (labels.length > 1 && SUFFIXES.has(labels[labels.length - 1])) {
    labels.pop();
  }
  const brand = labels[labels.length - 1] ?? host;
  return brand
    .split('-')
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

/** A publisher name fit to show a reader. Values that are already names —
 *  "The Guardian" — are passed through untouched. */
export function publisherName(raw?: string | null): string {
  if (!raw) return '';
  const trimmed = raw.trim();
  if (!trimmed) return '';

  const host = normalizeHost(trimmed);
  const curated = PUBLISHERS[host];
  if (curated) return curated;

  // Only rewrite things that are actually domains; leave real names alone.
  if (!looksLikeDomain(host)) return trimmed;

  return prettify(host);
}
