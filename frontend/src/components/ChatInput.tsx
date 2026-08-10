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

  // grow with content, up to a few lines
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
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
      className="flex items-end gap-2 rounded-2xl border border-ink-200 bg-white p-2 shadow-card transition-colors focus-within:border-brand-400 focus-within:ring-4 focus-within:ring-brand-100"
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
        className="flex-1 resize-none border-0 bg-transparent px-3 py-2 text-[15px] leading-relaxed text-ink-900 placeholder:text-ink-400 focus:outline-none focus:ring-0"
      />
      {busy && onStop ? (
        <button
          type="button"
          onClick={onStop}
          className="shrink-0 rounded-xl bg-ink-100 px-4 py-2.5 text-sm font-semibold text-ink-700 transition-colors hover:bg-ink-200"
        >
          Stop
        </button>
      ) : (
        <button
          type="submit"
          disabled={busy || !text.trim()}
          aria-label="Send message"
          className="shrink-0 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-ink-300"
        >
          Send
        </button>
      )}
    </form>
  );
}
