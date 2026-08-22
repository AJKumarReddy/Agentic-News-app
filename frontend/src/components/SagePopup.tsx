import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import ChatInput from './ChatInput';
import MessageBubble from './MessageBubble';
import SageAvatar from './SageAvatar';
import { deleteConversation, getConversation } from '../services/api';
import { useChat } from '../hooks/useChat';
import { useSpeech } from '../hooks/useSpeech';
import type { SpeechState } from '../types';
import { readStored, writeStored } from '../utils/storage';

/** The floating "Ask Sage" button and the panel it opens.
 *
 *  Search is the landing page, so a reader who thinks of a question is looking
 *  at articles, not at the chat. Sending them to /chat threw away what they
 *  were reading; the panel keeps the page underneath and answers beside it.
 *
 *  It is a real chat, not a preview: the same useChat hook, the same bubbles
 *  and the same composer as the full page, so answers stream and arrive cited
 *  exactly as they do there. A conversation started here is a normal
 *  conversation — "Open full view" carries it to /chat by id rather than
 *  restarting it, and it shows up in Recent chats like any other.
 *
 *  Never rendered on /chat, where Sage is already the whole page.
 */
/** Narrower than this and citations wrap to one word a line; the upper bound
 *  is computed per drag so the article grid always keeps a usable column. */
const MIN_WIDTH = 320;
const MAX_WIDTH = 760;

export default function SagePopup({
  voiceInput = false,
  voiceAvailable = false,
  autoRead = false,
  onConversationChange,
}: {
  voiceInput?: boolean;
  /** "Read answers aloud → Always on". Autoplay lived only on /chat, so the
   *  preference silently did nothing for answers given in this panel. */
  autoRead?: boolean;
  /** Lets the rail's Recent chats react to a thread started, or deleted, here. */
  onConversationChange?: () => void;
  /** The backend can speak. Without this the answers here had no playback
   *  control at all, while the same answers on /chat did. */
  voiceAvailable?: boolean;
}) {
  const { pathname } = useLocation();
  // open/closed survives a refresh: a reader mid-conversation who reloads an
  // article should not have to reopen Sage and lose the thread
  const [open, setOpen] = useState(() => readStored('sage-open') === 'yes');
  const { messages, setMessages, conversationId, setConversationId, busy, send, stop, reset } =
    useChat();
  const speech = useSpeech();
  // Width is the reader's, not ours: a citation-heavy answer wants more room
  // than a one-line one, and how much of the article grid they are willing to
  // give up is a judgement only they can make. Remembered between visits.
  const [width, setWidth] = useState(() => {
    const saved = Number(readStored('sage-width'));
    return Number.isFinite(saved) && saved >= MIN_WIDTH ? saved : 384;
  });
  const [dragging, setDragging] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const { speak: speakAudio, stop: stopSpeech } = speech;

  const handleSpeak = useCallback(
    (messageId: number) => {
      if (conversationId) speakAudio(conversationId, messageId);
    },
    [conversationId, speakAudio],
  );

  // a new question stops the previous answer talking over it
  const handleSend = useCallback(
    (text: string) => {
      stopSpeech();
      return send(text);
    },
    [send, stopSpeech],
  );

  // Both controls end the visible thread; they differ in what becomes of it.
  // The stored pointer is cleared either way — otherwise the next refresh
  // restores the conversation the reader just closed.
  const detach = useCallback(() => {
    stopSpeech();
    stop();
    reset();
    spokenRef.current.clear();
    writeStored('sage-conversation', '');
  }, [reset, stop, stopSpeech]);

  /** Keep it. The thread stays in Recent chats and can be reopened. */
  const startNew = useCallback(() => {
    detach();
    onConversationChange?.();
  }, [detach, onConversationChange]);

  /** Discard it. Deleted server-side, so it does not linger in the rail —
   *  "clear" that quietly kept a copy would be the opposite of the promise. */
  const clearChat = useCallback(async () => {
    const doomed = conversationId;
    detach();
    if (doomed) {
      try {
        await deleteConversation(doomed);
      } catch {
        // already gone, or the server refused; the panel is clear either way
      }
    }
    onConversationChange?.();
  }, [conversationId, detach, onConversationChange]);

  // Answers already played, and every message restored from history — a
  // reopened conversation must not read its whole backlog out loud. Seeded
  // from the restore path rather than from render timing, which cannot tell a
  // historical message from a new one.
  const spokenRef = useRef<Set<number>>(new Set());

  // Autoplay: the newest answer, once, and only when the reader asked for it.
  useEffect(() => {
    if (!autoRead || !voiceAvailable || !conversationId) return;
    const last = messages[messages.length - 1];
    if (!last || last.role !== 'assistant' || last.streaming || !last.content) return;
    if (last.id === undefined || spokenRef.current.has(last.id)) return;
    spokenRef.current.add(last.id);
    speakAudio(conversationId, last.id);
  }, [messages, autoRead, voiceAvailable, conversationId, speakAudio]);

  // a thread started here belongs in Recent chats like any other
  const announced = useRef<string | null>(null);
  useEffect(() => {
    if (conversationId && announced.current !== conversationId) {
      announced.current = conversationId;
      onConversationChange?.();
    }
  }, [conversationId, onConversationChange]);

  const speechStateFor = (id?: number): SpeechState => {
    if (id === undefined) return 'idle';
    if (speech.speakingId === id) return 'speaking';
    if (speech.loadingId === id) return 'loading';
    if (speech.errorId === id) return 'error';
    return 'idle';
  };

  // closing the panel should not leave Sage talking to an empty room
  useEffect(() => {
    if (!open) stopSpeech();
  }, [open, stopSpeech]);

  useEffect(() => writeStored('sage-open', open ? 'yes' : 'no'), [open]);

  // The thread itself is already on the server; only its id needs keeping.
  useEffect(() => {
    if (conversationId) writeStored('sage-conversation', conversationId);
  }, [conversationId]);

  // Restore it once, on mount. A stored id can be stale — the conversation may
  // have been deleted from the rail — so a failed load clears the pointer
  // rather than leaving a panel that fails the same way on every visit.
  const restored = useRef(false);
  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    const saved = readStored('sage-conversation');
    if (!saved) return;
    getConversation(saved)
      .then((detail) => {
        setConversationId(detail.id);
        setMessages(
          detail.messages.map((m) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            sources: m.sources || [],
          })),
        );
        // marked before they can reach the autoplay effect, so restoring a
        // conversation is silent however long it is
        detail.messages.forEach((m) => m.id !== undefined && spokenRef.current.add(m.id));
      })
      .catch(() => writeStored('sage-conversation', ''));
  }, [setConversationId, setMessages]);

  useEffect(() => writeStored('sage-width', String(width)), [width]);

  useEffect(() => {
    if (!dragging) return;
    const onMove = (event: MouseEvent) => {
      // the grid keeps at least 420px, so dragging can never squeeze the
      // articles into a column too narrow to read
      const ceiling = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, window.innerWidth - 420));
      setWidth(Math.min(Math.max(window.innerWidth - event.clientX, MIN_WIDTH), ceiling));
    };
    const stop = () => setDragging(false);
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', stop);
    return () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', stop);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
  }, [dragging]);

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, open]);

  // Escape closes, matching the mobile drawer. No outside-click handler: the
  // panel deliberately does not trap the page, and dismissing a half-typed
  // question because someone clicked an article behind it would lose work.
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open]);

  if (pathname.startsWith('/chat')) return null;

  return (
    <>
      {open && (
        <div
          ref={panelRef}
          role="dialog"
          aria-label="Ask Sage"
          // A column of the page, not a layer over it — the rail's mirror on
          // the other edge. From md it takes its own width and the article
          // grid reflows into what is left, so nothing a reader was looking at
          // is covered by the thing they opened to ask about it.
          //
          // Below md there is no room to give it a column, so there it behaves
          // like the navigation does at that size: a full-screen overlay.
          style={{ '--sage-w': `${width}px` } as React.CSSProperties}
          className="fixed inset-0 z-50 flex w-full animate-slide-in-right flex-col border-ink-200 bg-white shadow-lift dark:border-ink-700 dark:bg-ink-800 md:static md:relative md:z-auto md:w-[var(--sage-w)] md:shrink-0 md:animate-none md:border-l md:shadow-none"
        >
          {/* Drag handle. A separator role with arrow keys too — a resize that
              only a mouse can perform is a control some readers simply do not
              have. Hidden below md, where the panel is a full-screen overlay
              and there is nothing to resize against. */}
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize Sage panel"
            aria-valuenow={width}
            aria-valuemin={MIN_WIDTH}
            aria-valuemax={MAX_WIDTH}
            tabIndex={0}
            onMouseDown={(event) => {
              event.preventDefault();
              // synchronous, before the browser can start a selection — via
              // the effect below this landed a render late and the drag left
              // half the article grid highlighted
              document.body.style.userSelect = 'none';
              document.body.style.cursor = 'col-resize';
              window.getSelection()?.removeAllRanges();
              setDragging(true);
            }}
            onKeyDown={(event) => {
              if (event.key === 'ArrowLeft') setWidth((w) => Math.min(w + 24, MAX_WIDTH));
              if (event.key === 'ArrowRight') setWidth((w) => Math.max(w - 24, MIN_WIDTH));
            }}
            className={`absolute inset-y-0 left-0 z-10 hidden w-1.5 cursor-col-resize transition-colors md:block ${
              dragging ? 'bg-brand-500' : 'bg-transparent hover:bg-brand-300'
            } focus-visible:bg-brand-500 focus-visible:outline-none`}
          />

          <header className="flex shrink-0 items-center gap-2.5 border-b border-ink-200 bg-brand-600 px-4 py-3 pt-[max(0.75rem,env(safe-area-inset-top))] text-white dark:border-ink-700">
            <SageAvatar state={busy ? 'thinking' : 'idle'} className="h-8 w-8 shrink-0" />
            <span className="min-w-0 flex-1 leading-tight">
              <span className="block text-sm font-semibold">Sage</span>
              <span className="flex items-center gap-1.5 text-[11px] text-white/70">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-400" />
                {busy ? 'Researching…' : 'Online'}
              </span>
            </span>
            {/* a long thread outgrows a 24rem panel; this hands it to the page
                without losing it, which is why it carries the id */}
            {messages.length > 0 && (
              /* Two endings, named for what they do to the thread rather
                 than for how they look. A bare "+" read as "add something",
                 which is not what either of these is. */
              <>
                <button
                  onClick={startNew}
                  title="Keep this conversation and start another"
                  className="flex shrink-0 items-center gap-1 rounded-lg px-1.5 py-1 text-[11px] font-medium text-white/75 transition-colors hover:bg-white/15 hover:text-white"
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                    <path d="M12 5v14M5 12h14" />
                  </svg>
                  New
                </button>
                <button
                  onClick={clearChat}
                  title="Delete this conversation — it will not be kept in Recent chats"
                  className="flex shrink-0 items-center gap-1 rounded-lg px-1.5 py-1 text-[11px] font-medium text-white/75 transition-colors hover:bg-red-500/30 hover:text-white"
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" />
                  </svg>
                  Clear
                </button>
              </>
            )}
            {conversationId && (
              <Link
                to={`/chat?conversation=${conversationId}`}
                title="Continue this conversation on the full chat page"
                className="rounded-lg px-2 py-1 text-[11px] font-medium text-white/75 transition-colors hover:bg-white/15 hover:text-white"
              >
                Full view
              </Link>
            )}
            <button
              onClick={() => setOpen(false)}
              aria-label="Close Sage"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-white/75 transition-colors hover:bg-white/15 hover:text-white"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
          </header>

          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto overflow-x-hidden overscroll-contain bg-brand-soft px-3.5 py-4 dark:bg-brand-soft-dark">
            {/* mt-auto, not justify-end on the scroller above it. Both push a
                short thread down to the composer, but justify-end makes an
                overflowing thread spill past the *top* of the scroll box where
                no scrollbar can reach it — the panel simply stopped scrolling
                once the conversation grew past one screen. */}
            <div className="mt-auto space-y-3">
            {messages.length === 0 ? (
              <p className="rounded-2xl rounded-bl-md border border-ink-200 bg-white px-3.5 py-3 text-[14px] leading-relaxed text-ink-700 shadow-card dark:border-ink-700 dark:bg-ink-800 dark:text-ink-200">
                Hi, I&rsquo;m Sage <span aria-hidden="true">👋</span> Ask me anything — I&rsquo;ll
                research the sources, connect the evidence, and help you verify the answer.
              </p>
            ) : (
              messages.map((message, i) => (
                <MessageBubble
                  key={message.id ?? `pending-${i}`}
                  message={message}
                  speechState={speechStateFor(message.id)}
                  onSpeak={voiceAvailable ? handleSpeak : undefined}
                />
              ))
            )}
            <div ref={bottomRef} />
            </div>
          </div>

          {speech.autoplayBlocked && (
            /* Not an error state: the browser withheld audio for want of a
               gesture. Says what to do rather than what went wrong, and clears
               itself the moment anything plays. */
            <button
              onClick={() => {
                speech.dismissAutoplayPrompt();
                const last = messages[messages.length - 1];
                if (conversationId && last?.id !== undefined) handleSpeak(last.id);
              }}
              className="shrink-0 border-t border-accent-200 bg-accent-50 px-3 py-2.5 text-left text-[12px] font-medium text-accent-800 transition-colors hover:bg-accent-100 dark:border-accent-500/30 dark:bg-accent-500/10 dark:text-accent-200"
            >
              Tap once to enable automatic audio
            </button>
          )}

          <div className="shrink-0 border-t border-ink-200 px-3 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] dark:border-ink-700">
            <ChatInput
              onSend={handleSend}
              busy={busy}
              onStop={stop}
              placeholder="Ask Sage…"
              voiceInput={voiceInput}
            />
          </div>
        </div>
      )}

      {/* Not rendered while the panel is open: the panel occupies exactly
          where this sits, and the header's X is the close. Conditional rather
          than the `hidden` attribute, which loses to the button's own
          `display: flex` and left it sitting on top of the composer. */}
      {!open && (
      <button
        onClick={() => setOpen(true)}
        aria-label="Ask Sage"
        className="fixed bottom-[max(1.25rem,env(safe-area-inset-bottom))] right-4 z-40 flex items-center gap-2 rounded-full bg-brand-600 py-1.5 pl-1.5 pr-3 text-white shadow-glow transition-colors hover:bg-brand-700 sm:right-6 sm:pr-4"
      >
        <SageAvatar state={busy ? 'thinking' : 'idle'} className="h-9 w-9 shrink-0" />
        {/* the label is what makes it an invitation rather than decoration;
            below sm it would eat the width, so there it stays a circle */}
        <span className="hidden text-sm font-semibold sm:inline">Ask Sage</span>
      </button>
      )}
    </>
  );
}
