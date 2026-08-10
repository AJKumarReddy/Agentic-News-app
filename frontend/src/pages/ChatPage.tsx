import { useEffect, useRef } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import ChatInput from '../components/ChatInput';
import MessageBubble from '../components/MessageBubble';
import { getConversation } from '../services/api';
import { useChat } from '../hooks/useChat';

const SUGGESTED_QUESTIONS = [
  'Latest AI developments',
  'US politics this week',
  'Climate stories today',
  'Compare coverage of OpenAI and Anthropic',
];

export default function ChatPage({ onConversationChange }: { onConversationChange?: () => void }) {
  const { messages, setMessages, conversationId, setConversationId, busy, send, stop, reset } =
    useChat();
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const bottomRef = useRef<HTMLDivElement>(null);
  const notifiedRef = useRef<string | null>(null);

  // Load an existing conversation from ?conversation=<id>
  const requestedConversation = searchParams.get('conversation');
  useEffect(() => {
    if (!requestedConversation || requestedConversation === conversationId) return;
    getConversation(requestedConversation)
      .then((detail) => {
        setConversationId(detail.id);
        setMessages(
          detail.messages.map((m) => ({ role: m.role, content: m.content, sources: m.sources || [] })),
        );
      })
      .catch(() => undefined);
  }, [requestedConversation, conversationId, setConversationId, setMessages]);

  // Handle navigation state: new chat, or prefilled "Ask AI" question.
  // The ref guards against double-fire: StrictMode re-runs effects in dev,
  // and history.replaceState doesn't update the router's location.state.
  const handledNavState = useRef<unknown>(null);
  useEffect(() => {
    const state = location.state as { newChat?: number; prefill?: string; articleId?: string } | null;
    if (!state || handledNavState.current === location.state) return;
    handledNavState.current = location.state;
    if (state.newChat) reset();
    if (state.prefill) {
      // articleId travels with the first message; the server persists it as
      // active_article_id, so follow-up messages don't need to resend it
      send(state.prefill, state.articleId ?? null);
    }
    window.history.replaceState({}, '');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // refresh sidebar once a new conversation gets an id
  useEffect(() => {
    if (conversationId && notifiedRef.current !== conversationId) {
      notifiedRef.current = conversationId;
      onConversationChange?.();
    }
  }, [conversationId, onConversationChange]);

  const empty = messages.length === 0;

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-4 py-6">
          {empty ? (
            <div className="mt-16 text-center">
              <h1 className="font-serif text-3xl font-bold text-brand-900">News AI</h1>
              <p className="mt-2 text-slate-600">
                Research the news with AI — grounded answers, every claim cited.
              </p>
              <div className="mx-auto mt-8 grid max-w-xl grid-cols-1 gap-3 sm:grid-cols-2">
                {SUGGESTED_QUESTIONS.map((question) => (
                  <button
                    key={question}
                    onClick={() => send(question)}
                    className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-left text-sm text-slate-700 shadow-sm transition-colors hover:border-brand-500 hover:bg-brand-50"
                  >
                    {question}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {messages.map((message, index) => (
                <MessageBubble key={index} message={message} />
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>
      </div>
      <div className="border-t border-slate-200 bg-slate-50/80 backdrop-blur">
        <div className="mx-auto max-w-3xl px-4 py-4">
          <ChatInput onSend={send} busy={busy} onStop={stop} />
          <p className="mt-2 text-center text-[11px] text-slate-400">
            Answers cite their sources — Guardian reporting first, the web when needed. Verify
            important facts via the linked articles.
          </p>
        </div>
      </div>
    </div>
  );
}
