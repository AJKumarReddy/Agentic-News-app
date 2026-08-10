/** Sections offered in the UI. Ids are Guardian section ids (passed straight
 *  through) and are mapped to NYT desks/feeds server-side, so every entry
 *  works for both publishers. Grouped for the sidebar. */
export const SECTIONS = [
  { id: 'us-news', label: 'US News', group: 'News' },
  { id: 'world', label: 'World', group: 'News' },
  { id: 'politics', label: 'Politics', group: 'News' },
  { id: 'business', label: 'Business', group: 'News' },
  { id: 'money', label: 'Money', group: 'News' },

  { id: 'technology', label: 'Technology', group: 'Science & Tech' },
  { id: 'science', label: 'Science', group: 'Science & Tech' },
  { id: 'environment', label: 'Climate', group: 'Science & Tech' },
  { id: 'society', label: 'Health', group: 'Science & Tech' },

  { id: 'sport', label: 'Sport', group: 'Culture & Life' },
  { id: 'culture', label: 'Culture', group: 'Culture & Life' },
  { id: 'film', label: 'Film', group: 'Culture & Life' },
  { id: 'books', label: 'Books', group: 'Culture & Life' },
  { id: 'music', label: 'Music', group: 'Culture & Life' },
  { id: 'travel', label: 'Travel', group: 'Culture & Life' },
  { id: 'food', label: 'Food', group: 'Culture & Life' },
  { id: 'fashion', label: 'Fashion', group: 'Culture & Life' },
  { id: 'commentisfree', label: 'Opinion', group: 'Culture & Life' },
] as const;

export const SECTION_GROUPS = ['News', 'Science & Tech', 'Culture & Life'] as const;
