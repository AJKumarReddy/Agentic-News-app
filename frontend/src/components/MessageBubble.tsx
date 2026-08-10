import { memo } from 'react';
import Markdown from './Markdown';
import RouteBadge from './RouteBadge';
import SourceList from './SourceList';
import type { ChatMessage } from '../types';

// memo: while streaming, only the last bubble's props change — earlier
// messages must not re-render (and re-parse markdown) per token batch
function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === 'user') {
    return (
      <div className="flex animate-fade-up justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-md bg-brand-gradient px-4 py-2.5 shadow-glow text-[15px] leading-relaxed text-white shadow-sm">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex animate-fade-up justify-start">
      <div className="w-full max-w-[94%] rounded-2xl rounded-bl-md border border-ink-200 dark:border-ink-700 bg-white dark:bg-ink-800 px-5 py-4 shadow-card">
        {message.status && (
          <div className="flex items-center gap-2 py-1 text-sm text-ink-500 dark:text-ink-400 dark:text-ink-500">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-accent-500" />
            </span>
            {message.status}
          </div>
        )}

        {message.routing && !message.streaming && <RouteBadge routing={message.routing} />}

        {message.notice && !message.streaming && (
          <div className="mb-3 inline-flex items-center gap-1.5 rounded-md bg-warm-50 px-2.5 py-1 text-[11px] font-medium text-warm-800 dark:text-warm-200">
            <span aria-hidden="true">◷</span>
            {message.notice}
          </div>
        )}

        {message.content && <Markdown content={message.content} sources={message.sources} />}

        {message.streaming && message.content && (
          <span className="ml-0.5 inline-block h-4 w-[3px] animate-pulse rounded-full bg-brand-500 align-text-bottom" />
        )}

        {!message.streaming && <SourceList sources={message.sources} />}
      </div>
    </div>
  );
}

export default memo(MessageBubble);
