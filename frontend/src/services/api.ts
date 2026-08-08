import axios from 'axios';
import type {
  ArticleIntelligence,
  Article,
  ChatStreamEvent,
  ConversationSummary,
  SearchResponse,
  Source,
} from '../types';
import { SSEParser } from '../utils/sse';

export const API_BASE: string = import.meta.env.VITE_API_BASE_URL || '/api';

const http = axios.create({ baseURL: API_BASE, timeout: 30000 });

export interface SearchParams {
  q?: string;
  from_date?: string;
  to_date?: string;
  section?: string;
  tag?: string;
  author?: string;
  order_by?: 'newest' | 'oldest' | 'relevance';
  page?: number;
  page_size?: number;
}

export async function searchNews(params: SearchParams): Promise<SearchResponse> {
  const { data } = await http.get<SearchResponse>('/news/search', { params });
  return data;
}

export async function getArticle(articleId: string): Promise<Article> {
  const { data } = await http.get<Article>(`/news/article/${articleId}`);
  return data;
}

export async function getArticleIntelligence(articleId: string): Promise<ArticleIntelligence> {
  const { data } = await http.get<ArticleIntelligence>(`/news/article/${articleId}/intelligence`, {
    timeout: 90000,
  });
  return data;
}

export async function listConversations(): Promise<ConversationSummary[]> {
  const { data } = await http.get<ConversationSummary[]>('/conversations');
  return data;
}

export interface ConversationDetail {
  id: string;
  title: string;
  messages: { role: 'user' | 'assistant'; content: string; sources: Source[] }[];
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  const { data } = await http.get<ConversationDetail>(`/conversations/${id}`);
  return data;
}

/**
 * Streaming chat via fetch + SSE. Calls onEvent for every server event.
 * Returns when the stream closes; throws on network/HTTP failure.
 */
export async function streamChat(
  message: string,
  options: {
    conversationId?: string | null;
    articleId?: string | null;
    signal?: AbortSignal;
    onEvent: (event: ChatStreamEvent) => void;
  },
): Promise<void> {
  const response = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal: options.signal,
    body: JSON.stringify({
      message,
      conversation_id: options.conversationId || null,
      article_id: options.articleId || null,
      stream: true,
    }),
  });
  if (!response.ok || !response.body) {
    throw new Error(`Chat request failed (${response.status})`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = new SSEParser();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    for (const event of parser.feed(decoder.decode(value, { stream: true }))) {
      options.onEvent(event);
    }
  }
}

export async function checkHealth(): Promise<{ status: string }> {
  const { data } = await http.get('/health');
  return data;
}
