import { useCallback, useEffect, useRef } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import ArticleChip from '../components/ArticleChip';
import ChatInput from '../components/ChatInput';
import MessageBubble from '../components/MessageBubble';
import VoiceNudge from '../components/VoiceNudge';
import { getConversation } from '../services/api';
import { useChat } from '../hooks/useChat';
import { useSpeech } from '../hooks/useSpeech';
import type { useVoice } from '../hooks/useVoice';
import type { SpeechState } from '../types';
import SageAvatar from '../components/SageAvatar';

// each prompt gets its own accent so the grid reads as a palette, not a block
const SUGGESTIONS = [
  {
    label: "What are today's top stories?",
    hint: 'A cited round-up across newsrooms',
    accent: 'from-brand-500 to-brand-700',
  },
  {
    label: 'Catch me up on the past week',
    hint: 'What changed, and when',
    accent: 'from-accent-400 to-accent-600',
  },
  {
    label: 'How is AI regulation being covered?',
    hint: 'Compare outlets side by side',
    accent: 'from-warm-400 to-warm-600',
  },
  {
    label: "What's the latest on the economy?",
    hint: 'Follow an ongoing story',
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
  const navigate = useNavigate();
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

  /** The return leg of the panel's "Full view". Sends the reader back to the
   *  articles with this thread reopened beside them, rather than leaving the
   *  full page a one-way door. The id goes as navigation state because the
   *  panel never unmounts and so cannot pick it up any other way — see the
   *  handover effect in SagePopup. */
  const toSideView = useCallback(() => {
    stopSpeech();
    navigate('/search', { state: { dockSage: conversationId } });
  }, [conversationId, navigate, stopSpeech]);

  const empty = messages.length === 0;
  const hasAnswer = messages.some((m) => m.role === 'assistant' && !m.streaming && m.content);
  const showNudge = voice.available && !voice.nudged && hasAnswer;

  return (
    <div className="relative flex h-full flex-col bg-brand-soft dark:bg-brand-soft-dark">
      {/* Floated into the corner rather than given a bar of its own: one
          secondary control does not earn a strip across the top, and the
          thread is centred in a max-w-3xl column, so the space beside it is
          already empty. Tinted and blurred so it stays legible on a narrow
          viewport, where an answer can pass underneath it. */}
      {conversationId && (
        <button
          onClick={toSideView}
          disabled={busy}
          title={
            busy ? 'Wait for the answer to finish' : 'Continue this conversation beside the articles'
          }
          className="absolute right-3 top-3 z-20 flex items-center gap-1.5 rounded-lg border border-ink-200/70 bg-white/80 px-2 py-1 text-[11px] font-medium text-ink-500 shadow-card backdrop-blur transition-colors hover:border-ink-300 hover:bg-white hover:text-ink-800 disabled:cursor-not-allowed disabled:opacity-40 dark:border-ink-700/70 dark:bg-ink-900/70 dark:text-ink-400 dark:hover:bg-ink-800 dark:hover:text-ink-100 sm:right-4 sm:top-4"
        >
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <rect x="3" y="4" width="18" height="16" rx="2" />
            <path d="M15 4v16" />
          </svg>
          Side view
        </button>
      )}
      <div className="flex-1 overflow-y-auto overscroll-contain">
        <div className="mx-auto max-w-3xl px-3 py-6 sm:px-4 sm:py-8">
          {empty ? (
            <div className="mt-6 animate-fade-up text-center sm:mt-12">
              {/* Sage introduces itself here rather than the product doing it:
                  the empty chat is the one place the assistant has a turn of
                  its own, and a face makes the composer below it obvious. */}
              <SageAvatar className="mx-auto mb-4 h-16 w-16" />
              <h1 className="text-[26px] font-bold leading-tight tracking-tight text-ink-900 dark:text-ink-50 sm:text-[31px]">
                Meet Sage
              </h1>
              {/* Sage is introduced, not Source: the product is the shell the
                  reader is already inside, and this is the assistant's one
                  turn to say what it does. Names no publisher — the active set
                  is whichever keys are configured, so a list goes stale. */}
              <p className="mx-auto mt-2.5 max-w-lg text-[15px] leading-relaxed text-ink-600 dark:text-ink-300">
                Your AI research guide. Ask a question, and Sage will research the sources, connect
                the evidence, and give you an answer you can verify.
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
