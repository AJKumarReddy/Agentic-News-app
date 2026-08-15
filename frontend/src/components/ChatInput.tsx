import { FormEvent, useEffect, useRef, useState } from 'react';

export default function ChatInput({
  onSend,
  busy,
  onStop,
  placeholder = 'Ask about the news…',
}: {
  onSend: (text: string) => void;
  busy: boolean;
  onStop?: () => void;
  placeholder?: string;
}) {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

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
  );
}
