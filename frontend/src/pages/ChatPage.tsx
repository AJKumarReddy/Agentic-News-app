import { useEffect, useRef, useState } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import ChatInput from '../components/ChatInput';
import MessageBubble from '../components/MessageBubble';
import { getConversation } from '../services/api';
import { useChat } from '../hooks/useChat';

const SUGGESTED_QUESTIONS = [
  'Latest AI developments',
  'US politics this week',
  'Climate stories today',
  'Compare Guardian coverage of OpenAI and Anthropic',
];

export default function ChatPage({ onConversationChange }: { onConversationChange?: () => void }) {
  const { messages, setMessages, conversationId, setConversationId, busy, send, stop, reset } =
    useChat();
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const [pendingArticleId, setPendingArticleId] = useState<string | null>(null);
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

  // Handle navigation state: new chat, or prefilled "Ask AI" question
  useEffect(() => {
    const state = location.state as { newChat?: number; prefill?: string; articleId?: string } | null;
    if (!state) return;
    if (state.newChat) reset();
    if (state.prefill) {
      setPendingArticleId(state.articleId ?? null);
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
              <h1 className="font-serif text-3xl font-bold text-guardian-900">
                Guardian AI News Assistant
              </h1>
              <p className="mt-2 text-slate-600">
                Research Guardian journalism using AI — grounded answers with citations.
              </p>
              <div className="mx-auto mt-8 grid max-w-xl grid-cols-1 gap-3 sm:grid-cols-2">
                {SUGGESTED_QUESTIONS.map((question) => (
                  <button
                    key={question}
                    onClick={() => send(question)}
                    className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-left text-sm text-slate-700 shadow-sm transition-colors hover:border-guardian-500 hover:bg-guardian-50"
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
          <ChatInput
            onSend={(text) => {
              send(text, pendingArticleId);
              setPendingArticleId(null);
            }}
            busy={busy}
            onStop={stop}
          />
          <p className="mt-2 text-center text-[11px] text-slate-400">
            Answers are grounded in Guardian reporting with citations. Verify important facts via the
            linked articles.
          </p>
        </div>
      </div>
    </div>
  );
}
