export interface Article {
  article_id: string;
  headline: string;
  section: string;
  author: string;
  published_at: string | null;
  url: string;
  thumbnail: string;
  trail_text: string;
  body_text?: string;
  tags: string[];
  source: string;
}

export interface SearchResponse {
  total: number;
  page: number;
  pages: number;
  page_size: number;
  articles: Article[];
}

export interface Source {
  n: number;
  /** "guardian" for Guardian articles, "web" for supplementary web results */
  type?: 'guardian' | 'web';
  /** Display name: "The Guardian" or the web source's domain */
  source?: string;
  article_id: string;
  headline: string;
  url: string;
  published_at: string;
  section: string;
  author: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  sources: Source[];
  status?: string; // transient pipeline status while streaming
  /** Retrieval metadata (e.g. "showing the last 14 days") shown as a badge,
   *  deliberately kept out of the answer prose. */
  notice?: string;
  streaming?: boolean;
}

export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ArticleAnalysis {
  summary: string;
  key_points: string[];
  entities: string[];
  topics: string[];
  important_dates: string[];
}

export interface ArticleIntelligence {
  article: Article;
  analysis: ArticleAnalysis;
  related: Article[];
}

export type ChatStreamEvent =
  | { type: 'state'; conversation_id: string }
  | { type: 'status'; stage: string; detail: string }
  | { type: 'token'; delta: string }
  | { type: 'sources'; sources: Source[] }
  | { type: 'notice'; detail: string }
  | { type: 'done' }
  | { type: 'error'; detail: string };
