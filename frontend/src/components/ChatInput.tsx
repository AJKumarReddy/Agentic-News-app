import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import MicButton from './MicButton';
import { recordingSupported, useRecorder } from '../hooks/useRecorder';
import { appendTranscript } from '../utils/transcript';

export default function ChatInput({
  onSend,
  busy,
  onStop,
  placeholder = 'Ask about the news…',
  voiceInput = false,
  maxRecordingSeconds = 60,
}: {
  onSend: (text: string) => void;
  busy: boolean;
  onStop?: () => void;
  placeholder?: string;
  /** The backend can transcribe. The browser still has to be able to record. */
  voiceInput?: boolean;
  maxRecordingSeconds?: number;
}) {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // The transcript lands in the box rather than being sent: speech-to-text
  // mishears exactly the proper nouns a news question turns on, and a wrong
  // question sent automatically costs a retrieval and an answer to undo.
  const receive = useCallback((incoming: string) => {
    setText((current) => appendTranscript(current, incoming));
    const el = textareaRef.current;
    if (el) {
      el.focus();
      // put the caret after what was just inserted, so typing continues the
      // sentence rather than landing wherever the caret happened to be
      requestAnimationFrame(() => el.setSelectionRange(el.value.length, el.value.length));
    }
  }, []);

  const recorder = useRecorder({ maxSeconds: maxRecordingSeconds, onTranscript: receive });
  // `recordingSupported` reads window, so it is called during render rather
  // than at module load — jsdom and SSR both lack it at import time
  const showMic = voiceInput && recordingSupported();

  // grow with content, up to a few lines — but never past ~30% of the viewport,
  // or on a short screen (phone in landscape, keyboard up) the box eats the chat
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    const cap = Math.max(72, Math.min(160, window.innerHeight * 0.3));
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, cap)}px`;
  }, [text]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (busy || !text.trim()) return;
    onSend(text);
    setText('');
  };

  return (
    <>
      {/* A blocked microphone is a browser-level setting this page cannot fix,
          so it has to be said in words — the button alone returning to rest
          looks like nothing happened. */}
      {showMic && recorder.error && (
        <p role="alert" className="mb-1.5 px-1 text-[12px] text-red-600 dark:text-red-400">
          {recorder.error}
        </p>
      )}
      <form
        onSubmit={submit}
        className="flex items-end gap-2 rounded-2xl border border-ink-200 dark:border-ink-700 bg-white dark:bg-ink-800 p-2 shadow-card transition-colors focus-within:border-accent-400 focus-within:ring-4 focus-within:ring-accent-100 dark:focus-within:ring-accent-500/20"
      >
      <textarea
        ref={textareaRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            submit(e);
          }
        }}
        rows={1}
        maxLength={4000}
        placeholder={placeholder}
        enterKeyHint="send"
        /* text-base = 16px: mobile Safari/Chrome zoom into any field below that
           on focus, and the reader has to pinch back out after every message */
        className="flex-1 resize-none border-0 bg-transparent px-2 py-2.5 text-base leading-relaxed text-ink-900 placeholder:text-ink-400 focus:outline-none focus:ring-0 dark:text-ink-50 dark:placeholder:text-ink-500 sm:px-3 sm:py-2 sm:text-[15px]"
      />
      {/* left of Send, so the pair reads as the two ways to put a question
          here — and so Send never moves when the mic is unavailable */}
      {showMic && (
        <MicButton state={recorder.state} seconds={recorder.seconds} onToggle={recorder.toggle} />
      )}
      {busy && onStop ? (
        <button
          type="button"
          onClick={onStop}
          className="min-h-[44px] shrink-0 rounded-xl bg-ink-100 dark:bg-ink-700 px-4 py-2.5 text-sm font-semibold text-ink-700 dark:text-ink-200 transition-colors hover:bg-ink-200 dark:hover:bg-ink-600"
        >
          Stop
        </button>
      ) : (
        <button
          type="submit"
          disabled={busy || !text.trim()}
          aria-label="Send message"
          className="min-h-[44px] shrink-0 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-ink-300 dark:disabled:bg-ink-700 dark:disabled:text-ink-500"
        >
          Send
        </button>
      )}
      </form>
    </>
  );
}
