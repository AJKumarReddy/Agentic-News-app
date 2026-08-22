/** Sections offered in the UI — the standard newsroom desks, and only those.
 *
 *  Ids are Guardian section ids (passed straight through) and are mapped to
 *  NYT desks and TheNewsAPI categories server-side, so every entry works for
 *  every publisher.
 *
 *  Deliberately short. The list was eighteen entries across three groups,
 *  which put Fashion, Books and Travel at the same weight as Politics and
 *  World in a rail people scan for the news. Narrower subjects are still
 *  reachable — they are ordinary search queries, and the backend widens a
 *  desk into its neighbours anyway (see backend/app/sources/sections.py), so
 *  Climate reporting still surfaces under Science.
 */
export const SECTIONS = [
  { id: 'us-news', label: 'US News' },
  { id: 'world', label: 'World' },
  { id: 'politics', label: 'Politics' },
  { id: 'business', label: 'Business' },
  { id: 'technology', label: 'Technology' },
  { id: 'science', label: 'Science' },
  { id: 'society', label: 'Health' },
  { id: 'sport', label: 'Sport' },
  { id: 'culture', label: 'Culture' },
  { id: 'commentisfree', label: 'Opinion' },
] as const;
