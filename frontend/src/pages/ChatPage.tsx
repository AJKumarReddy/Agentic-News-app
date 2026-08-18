import { useCallback, useEffect, useRef } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import ArticleChip from '../components/ArticleChip';
import ChatInput from '../components/ChatInput';
import MessageBubble from '../components/MessageBubble';
import VoiceNudge from '../components/VoiceNudge';
import { getConversation } from '../services/api';
import { useChat } from '../hooks/useChat';
import { useSpeech } from '../hooks/useSpeech';
import type { useVoice } from '../hooks/useVoice';
import type { SpeechState } from '../types';
import { LogoMark } from '../components/Logo';

// each prompt gets its own accent so the grid reads as a palette, not a block
const SUGGESTIONS = [
  { label: 'Top US news today', hint: 'Latest across newsrooms', accent: 'from-brand-500 to-brand-700' },
  { label: 'US politics this week', hint: 'What changed and when', accent: 'from-accent-400 to-accent-600' },
  { label: 'Latest AI developments', hint: 'Technology coverage', accent: 'from-warm-400 to-warm-600' },
  {
    label: 'Compare coverage of OpenAI and Anthropic',
    hint: 'Side-by-side reporting',
    accent: 'from-brand-400 to-accent-500',
  },
];

export default function ChatPage({
  onConversationChange,
  voice,
  voiceInput = false,
}: {
  onConversationChange?: () => void;
  voice: ReturnType<typeof useVoice>;
  /** The backend can transcribe a recording, so the composer may offer a mic. */
  voiceInput?: boolean;
}) {
  const {
    messages,
    setMessages,
    conversationId,
    setConversationId,
    activeArticle,
    setActiveArticle,
    clearArticle,
    busy,
    send,
    stop,
    reset,
  } = useChat();
  const speech = useSpeech();
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
          detail.messages.map((m) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            sources: m.sources || [],
          })),
        );
        // a reopened chat is still anchored to whatever it was anchored to
        const pinned = detail.state?.active_article_id;
        setActiveArticle(
          pinned
            ? { article_id: pinned, headline: detail.state?.active_article_headline || '' }
            : null,
        );
      })
      .catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedConversation, conversationId, setConversationId, setMessages, setActiveArticle]);

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

  const { speak: speakAudio, stop: stopSpeech } = speech;
  // Answers already played, or loaded from history and therefore never to be
  // played unasked. Reopening a chat should be silent.
  const spokenRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    if (!requestedConversation) return;
    messages.forEach((m) => m.id !== undefined && spokenRef.current.add(m.id));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedConversation, messages.length]);

  // Autoplay: the newest answer, once, only when the reader asked for it.
  useEffect(() => {
    if (voice.voice !== 'on' || !conversationId) return;
    const last = messages[messages.length - 1];
    if (!last || last.role !== 'assistant' || last.streaming || !last.content) return;
    if (last.id === undefined || spokenRef.current.has(last.id)) return;
    spokenRef.current.add(last.id);
    speakAudio(conversationId, last.id);
  }, [messages, voice.voice, conversationId, speakAudio]);

  // A new question stops the previous answer talking over it.
  const handleSend = useCallback(
    (text: string, articleId?: string | null) => {
      stopSpeech();
      return send(text, articleId);
    },
    [send, stopSpeech],
  );

  const handleSpeak = useCallback(
    (messageId: number) => {
      if (conversationId) speakAudio(conversationId, messageId);
    },
    [conversationId, speakAudio],
  );

  const speechStateFor = (id?: number): SpeechState => {
    if (id === undefined) return 'idle';
    if (speech.speakingId === id) return 'speaking';
    if (speech.loadingId === id) return 'loading';
    if (speech.errorId === id) return 'error';
    return 'idle';
  };

  const empty = messages.length === 0;
  const hasAnswer = messages.some((m) => m.role === 'assistant' && !m.streaming && m.content);
  const showNudge = voice.available && !voice.nudged && hasAnswer;

  return (
    <div className="flex h-full flex-col bg-brand-soft dark:bg-brand-soft-dark">
      <div className="flex-1 overflow-y-auto overscroll-contain">
        <div className="mx-auto max-w-3xl px-3 py-6 sm:px-4 sm:py-8">
          {empty ? (
            <div className="mt-6 animate-fade-up text-center sm:mt-12">
              <div className="mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-xl border border-ink-200 bg-white text-brand-600 shadow-card dark:border-ink-700 dark:bg-ink-800">
                <LogoMark className="h-6 w-6" />
              </div>
              <h1 className="font-serif text-[28px] font-bold leading-tight text-ink-900 dark:text-ink-50 sm:text-[34px]">
                News AI
              </h1>
              <p className="mx-auto mt-2.5 max-w-md text-[15px] leading-relaxed text-ink-600 dark:text-ink-300">
                Ask anything about the news. Answers are grounded in reporting from The Guardian and
                The New York Times, with every claim cited.
              </p>

              <div className="mx-auto mt-7 grid max-w-2xl grid-cols-1 gap-2.5 sm:mt-9 sm:grid-cols-2">
                {SUGGESTIONS.map((item) => (
                  <button
                    key={item.label}
                    onClick={() => send(item.label)}
                    className="group relative min-h-[64px] overflow-hidden rounded-xl border border-ink-200 dark:border-ink-700 bg-white dark:bg-ink-800 p-3.5 pl-5 text-left shadow-card transition-all hover:-translate-y-0.5 hover:border-brand-300 hover:shadow-lift active:scale-[0.99]"
                  >
                    <span
                      className={`absolute inset-y-0 left-0 w-1.5 bg-gradient-to-b ${item.accent}`}
                      aria-hidden="true"
                    />
                    <span className="block text-sm font-semibold text-ink-800 dark:text-ink-100 group-hover:text-brand-700 dark:group-hover:text-brand-300">
                      {item.label}
                    </span>
                    <span className="mt-0.5 block text-xs text-ink-500 dark:text-ink-400">{item.hint}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-5">
              {messages.map((message, index) => (
                <MessageBubble
                  key={index}
                  message={message}
                  speechState={speechStateFor(message.id)}
                  onSpeak={voice.available ? handleSpeak : undefined}
                />
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>
      </div>

      {/* pb clears the iPhone home indicator / Android gesture bar, which sits
          over the composer once viewport-fit=cover extends the page under it */}
      <div className="shrink-0 border-t border-ink-200 dark:border-ink-700 bg-white/80 dark:bg-ink-900/80 backdrop-blur">
        <div className="mx-auto max-w-3xl px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 sm:px-4 sm:pb-4 sm:pt-4">
          {showNudge && (
            <VoiceNudge onEnable={() => voice.setVoice('on')} onDismiss={voice.dismissNudge} />
          )}
          {activeArticle && <ArticleChip article={activeArticle} onClear={clearArticle} />}
          <ChatInput onSend={handleSend} busy={busy} onStop={stop} voiceInput={voiceInput} />
          <p className="mt-2 text-center text-[11px] leading-tight text-ink-400 dark:text-ink-500 sm:mt-2.5">
            Every claim is cited.{' '}
            <span className="hidden sm:inline">Verify important facts through the linked articles.</span>
            <span className="sm:hidden">Verify important facts.</span>
          </p>
        </div>
      </div>
    </div>
  );
}
