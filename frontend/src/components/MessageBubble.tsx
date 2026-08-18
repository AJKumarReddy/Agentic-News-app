import { memo } from 'react';
import Markdown from './Markdown';
import RouteBadge from './RouteBadge';
import SourceList from './SourceList';
import VoiceIcon from './VoiceIcon';
import type { ChatMessage, SpeechState } from '../types';

// The tooltip: the fuller sentence, room for the detail the button face
// cannot hold.
const SPEECH_LABELS: Record<SpeechState, string> = {
  idle: 'Read this answer aloud',
  loading: 'Preparing audio…',
  speaking: 'Stop reading',
  error: 'Audio unavailable — try again',
};

// The button face. An equalizer glyph alone never said what the control did,
// and a tooltip is not an answer on a touchscreen — so the name is written
// out, and it is the accessible name too rather than a second wording that
// speech control would fail to match.
const SPEECH_ACTIONS: Record<SpeechState, string> = {
  idle: 'Read aloud',
  loading: 'Preparing…',
  speaking: 'Stop reading',
  error: 'Audio unavailable',
};

// memo: while streaming, only the last bubble's props change — earlier
// messages must not re-render (and re-parse markdown) per token batch.
// `onSpeak` must therefore be a stable callback and `speechState` must be
// derived per message, so only the bubble that changed state re-renders.
function MessageBubble({
  message,
  speechState = 'idle',
  onSpeak,
}: {
  message: ChatMessage;
  speechState?: SpeechState;
  onSpeak?: (messageId: number) => void;
}) {
  if (message.role === 'user') {
    return (
      <div className="flex animate-fade-up justify-end">
        <div className="max-w-[88%] [overflow-wrap:anywhere] rounded-2xl rounded-br-md bg-brand-600 px-4 py-2.5 text-[15px] leading-relaxed text-white sm:max-w-[80%]">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex animate-fade-up justify-start">
      {/* full width below sm: at 360px, 6% plus px-5 was ~40px of the screen
          spent on padding around an already narrow column of text */}
      <div className="w-full max-w-full rounded-2xl rounded-bl-md border border-ink-200 dark:border-ink-700 bg-white dark:bg-ink-800 px-4 py-3.5 shadow-card sm:max-w-[94%] sm:px-5 sm:py-4">
        {message.status && (
          <div className="flex items-center gap-2 py-1 text-sm text-ink-500 dark:text-ink-400">
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

        {!message.streaming && onSpeak && message.id !== undefined && message.content && (
          <div className="mt-3 flex items-center gap-2">
            <button
              onClick={() => onSpeak(message.id as number)}
              title={SPEECH_LABELS[speechState]}
              className={`inline-flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-[11px] font-medium transition-colors ${
                speechState === 'speaking'
                  ? 'border-accent-300 bg-accent-50 text-accent-600 dark:border-accent-500/40 dark:bg-accent-500/15 dark:text-accent-300'
                  : speechState === 'error'
                    ? 'border-ink-200 text-ink-300 dark:border-ink-700 dark:text-ink-600'
                    : 'border-ink-200 text-ink-400 hover:border-accent-300 hover:text-accent-600 dark:border-ink-700 dark:text-ink-400 dark:hover:text-accent-300'
              }`}
            >
              <VoiceIcon state={speechState} className="h-3.5 w-3.5 shrink-0" />
              {SPEECH_ACTIONS[speechState]}
            </button>
            <span className="sr-only" role="status" aria-live="polite">
              {speechState === 'speaking' ? 'Reading the answer aloud' : ''}
            </span>
          </div>
        )}

        {!message.streaming && <SourceList sources={message.sources} />}
      </div>
    </div>
  );
}

export default memo(MessageBubble);
