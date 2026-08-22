import { memo } from 'react';
import Markdown from './Markdown';
import RouteBadge from './RouteBadge';
import SageAvatar from './SageAvatar';
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
    <div className="flex animate-fade-up items-start justify-start gap-2.5">
      {/* Sage answers, so Sage's face is on the answer. Hidden below sm, where
          the avatar plus its gap costs more of a 360px screen than it earns. */}
      <SageAvatar
        state={message.streaming || message.status ? 'thinking' : 'idle'}
        className="mt-0.5 hidden h-8 w-8 shrink-0 sm:block"
      />
      {/* full width below sm: at 360px, 6% plus px-5 was ~40px of the screen
          spent on padding around an already narrow column of text */}
      <div className="w-full min-w-0 max-w-full rounded-2xl rounded-bl-md border border-ink-200 dark:border-ink-700 bg-white dark:bg-ink-800 px-4 py-3.5 shadow-card sm:px-5 sm:py-4">
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

        {/* The `relative` below is load-bearing. Tailwind's sr-only is
            position:absolute with no offsets, so without a positioned ancestor
            the live region's containing block is the page itself: it escapes
            this scrolling thread and lands at its static position in *document*
            coordinates, far below the fold. That stretched the document and
            left a strip of blank space under the composer that the whole page
            could scroll down into. Contained here, it cannot reach the page. */}
        {!message.streaming && onSpeak && message.id !== undefined && message.content && (
          <div className="relative mt-3 flex items-center gap-2">
            <button
              onClick={() => onSpeak(message.id as number)}
              title={SPEECH_LABELS[speechState]}
              // Was a 11px ghost outline in ink-400 — the same weight as a
              // disabled control, so it read as decoration and people missed
              // it. Now a filled tint at body size: still secondary to the
              // answer, but plainly a button you can press.
              className={`inline-flex h-9 items-center gap-2 rounded-lg border px-3 text-[13px] font-semibold transition-colors ${
                speechState === 'speaking'
                  ? 'border-accent-400 bg-accent-100 text-accent-800 dark:border-accent-500/50 dark:bg-accent-500/25 dark:text-accent-100'
                  : speechState === 'error'
                    ? 'border-ink-200 text-ink-400 dark:border-ink-700 dark:text-ink-500'
                    : 'border-brand-200 bg-brand-50 text-brand-700 hover:border-brand-300 hover:bg-brand-100 dark:border-brand-500/30 dark:bg-brand-500/10 dark:text-brand-200 dark:hover:bg-brand-500/20'
              }`}
            >
              <VoiceIcon state={speechState} className="h-4 w-4 shrink-0" />
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
