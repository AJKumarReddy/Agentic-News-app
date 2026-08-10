import { FormEvent, useState } from 'react';

export default function ChatInput({
  onSend,
  busy,
  onStop,
  placeholder = 'Ask about Guardian news…',
}: {
  onSend: (text: string) => void;
  busy: boolean;
  onStop?: () => void;
  placeholder?: string;
}) {
  const [text, setText] = useState('');

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (busy || !text.trim()) return;
    onSend(text);
    setText('');
  };

  return (
    <form onSubmit={submit} className="flex items-end gap-2">
      <textarea
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
        className="flex-1 resize-none rounded-xl border border-slate-300 bg-white px-4 py-3 text-[15px] shadow-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
      />
      {busy && onStop ? (
        <button
          type="button"
          onClick={onStop}
          className="rounded-xl bg-slate-200 px-5 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-300"
        >
          Stop
        </button>
      ) : (
        <button
          type="submit"
          disabled={busy || !text.trim()}
          className="rounded-xl bg-brand-600 px-5 py-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Send
        </button>
      )}
    </form>
  );
}
