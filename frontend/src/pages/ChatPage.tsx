import { useEffect, useRef } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import ChatInput from '../components/ChatInput';
import MessageBubble from '../components/MessageBubble';
import { getConversation } from '../services/api';
import { useChat } from '../hooks/useChat';

const SUGGESTIONS = [
  { label: 'Top US news today', hint: 'Latest across newsrooms' },
  { label: 'US politics this week', hint: 'What changed and when' },
  { label: 'Latest AI developments', hint: 'Technology coverage' },
  { label: 'Compare coverage of OpenAI and Anthropic', hint: 'Side-by-side reporting' },
];

export default function ChatPage({ onConversationChange }: { onConversationChange?: () => void }) {
  const { messages, setMessages, conversationId, setConversationId, busy, send, stop, reset } =
    useChat();
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const bottomRef = useRef<HTMLDivElement>(null);
  const notifiedRef = useRef<string | null>(null);

  const requestedConversation = searchParams.get('conversation');
  // tracks whether the visible chat came from the URL, so navigating away
  // from it (back button, logo) clears it — but an in-progress new chat,
  // which has an id without a URL param, is never wiped
  const openedFromUrl = useRef(false);

  useEffect(() => {
    if (!requestedConversation) {
      if (openedFromUrl.current) {
        openedFromUrl.current = false;
        reset();
      }
      return;
    }
    if (requestedConversation === conversationId) return;
    getConversation(requestedConversation)
      .then((detail) => {
        openedFromUrl.current = true;
        setConversationId(detail.id);
        setMessages(
          detail.messages.map((m) => ({ role: m.role, content: m.content, sources: m.sources || [] })),
        );
      })
      .catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedConversation, conversationId, setConversationId, setMessages]);

  // Guarded against StrictMode double-invocation, which previously sent
  // "Ask AI" questions twice and interleaved two streams into one bubble.
  const handledNavState = useRef<unknown>(null);
  useEffect(() => {
    const state = location.state as { newChat?: number; prefill?: string; articleId?: string } | null;
    if (!state || handledNavState.current === location.state) return;
    handledNavState.current = location.state;
    if (state.newChat) reset();
    if (state.prefill) send(state.prefill, state.articleId ?? null);
    window.history.replaceState({}, '');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (conversationId && notifiedRef.current !== conversationId) {
      notifiedRef.current = conversationId;
      onConversationChange?.();
    }
  }, [conversationId, onConversationChange]);

  const empty = messages.length === 0;

  return (
    <div className="flex h-full flex-col bg-ink-50">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-4 py-8">
          {empty ? (
            <div className="mt-12 animate-fade-up text-center">
              <div className="mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-brand-600 text-xl font-bold text-white shadow-lift">
                N
              </div>
              <h1 className="font-serif text-[34px] font-bold leading-tight text-ink-900">News AI</h1>
              <p className="mx-auto mt-2.5 max-w-md text-[15px] leading-relaxed text-ink-600">
                Ask anything about the news. Answers are grounded in reporting from The Guardian and
                The New York Times, with every claim cited.
              </p>

              <div className="mx-auto mt-9 grid max-w-2xl grid-cols-1 gap-2.5 sm:grid-cols-2">
                {SUGGESTIONS.map((item) => (
                  <button
                    key={item.label}
                    onClick={() => send(item.label)}
                    className="group rounded-xl border border-ink-200 bg-white p-3.5 text-left shadow-card transition-all hover:-translate-y-0.5 hover:border-brand-300 hover:shadow-lift"
                  >
                    <span className="block text-sm font-semibold text-ink-800 group-hover:text-brand-700">
                      {item.label}
                    </span>
                    <span className="mt-0.5 block text-xs text-ink-500">{item.hint}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-5">
              {messages.map((message, index) => (
                <MessageBubble key={index} message={message} />
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>
      </div>

      <div className="border-t border-ink-200 bg-white/70 backdrop-blur">
        <div className="mx-auto max-w-3xl px-4 py-4">
          <ChatInput onSend={send} busy={busy} onStop={stop} />
          <p className="mt-2.5 text-center text-[11px] text-ink-400">
            Every claim is cited. Verify important facts through the linked articles.
          </p>
        </div>
      </div>
    </div>
  );
}
