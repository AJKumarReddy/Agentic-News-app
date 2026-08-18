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
  source_id?: string;
}

export interface NewsSourceInfo {
  id: string;
  name: string;
  domain: string;
}

export interface SearchResponse {
  total: number;
  page: number;
  pages: number;
  page_size: number;
  articles: Article[];
  /**
   * Publisher ids that could not be reached, whose articles on this page came
   * from our own store instead of a live fetch. Empty on a fully live result.
   */
  degraded_sources?: string[];
}

export interface Source {
  n: number;
  /** "publisher" for indexed journalism, "web" for supplementary web results */
  type?: 'publisher' | 'guardian' | 'web';
  /** Machine id of the publisher: "guardian" | "nyt" */
  source_id?: string;
  /** Display name: "The Guardian", "The New York Times", or a web domain */
  source?: string;
  article_id: string;
  headline: string;
  url: string;
  published_at: string;
  section: string;
  author: string;
}

export type ChatRoute = 'ARTICLE' | 'NEWS' | 'WEB' | 'BOTH' | 'DECLINE';

export interface RouteDecision {
  route: ChatRoute;
  intent: string;
  /** The message rewritten as a self-contained question before searching */
  standalone_question: string;
}

export interface ChatMessage {
  /** Server-side id of the stored row. Absent while a turn is still
   *  streaming, and it is what playback asks for — addressing by position in
   *  this array would speak the wrong answer the moment the two lists drift. */
  id?: number;
  role: 'user' | 'assistant';
  content: string;
  sources: Source[];
  routing?: RouteDecision;
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

/** The article a conversation is currently anchored to. Questions that refer
 *  back to it ("what does it say about X") are answered from it directly. */
export interface ActiveArticle {
  article_id: string;
  headline: string;
}

export type ChatStreamEvent =
  | { type: 'state'; conversation_id: string }
  | { type: 'status'; stage: string; detail: string }
  | { type: 'token'; delta: string }
  | { type: 'sources'; sources: Source[] }
  | { type: 'notice'; detail: string }
  | { type: 'route'; decision: RouteDecision }
  | { type: 'article'; article: ActiveArticle }
  | { type: 'done'; message_id?: number }
  | { type: 'error'; detail: string };

/** What this deployment can actually do, so the UI never renders a control
 *  the backend cannot serve. */
export interface Capabilities {
  tts: boolean;
  stt: boolean;
}

/** Playback state for one answer. */
export type SpeechState = 'idle' | 'loading' | 'speaking' | 'error';

/** Capture state for one spoken question. Mirrors SpeechState: the same four
 *  shapes — resting, working, active, failed — read from the other end. */
export type RecordingState = 'idle' | 'recording' | 'transcribing' | 'error';
