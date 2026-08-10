import { memo } from 'react';
import Markdown from './Markdown';
import SourceList from './SourceList';
import type { ChatMessage } from '../types';

// memo: while streaming, only the last bubble's props change — earlier
// messages must not re-render (and re-parse markdown) per token batch
function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-guardian-600 px-4 py-2.5 text-[15px] text-white shadow-sm">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[92%] w-full rounded-2xl rounded-bl-sm bg-white px-5 py-4 shadow-sm border border-slate-100">
        {message.status && (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <span className="h-2 w-2 animate-pulse rounded-full bg-guardian-500" />
            {message.status}
          </div>
        )}
        {message.content && <Markdown content={message.content} sources={message.sources} />}
        {message.streaming && message.content && (
          <span className="ml-1 inline-block h-4 w-1.5 animate-pulse bg-guardian-500 align-text-bottom" />
        )}
        {!message.streaming && <SourceList sources={message.sources} />}
      </div>
    </div>
  );
}

export default memo(MessageBubble);
