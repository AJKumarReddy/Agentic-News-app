import type { RecordingState } from '../types';

/** The name of the control in each state. Unlike the playback button in
 *  MessageBubble there is no room in the composer for a written label beside
 *  Send, so this is the accessible name rather than a second wording — a
 *  microphone glyph is unambiguous in a way the equalizer glyph was not. The
 *  elapsed time is the one thing that does show, because it is the only part
 *  a mic icon cannot convey. */
const LABELS: Record<RecordingState, string> = {
  idle: 'Ask by voice',
  recording: 'Stop recording',
  transcribing: 'Turning your recording into text',
  error: 'Ask by voice',
};

function clock(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, '0')}`;
}

const MicGlyph = (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <rect x="9" y="2" width="6" height="11" rx="3" />
    <path d="M5 11a7 7 0 0014 0M12 18v3" />
  </svg>
);

export default function MicButton({
  state,
  seconds,
  onToggle,
}: {
  state: RecordingState;
  seconds: number;
  onToggle: () => void;
}) {
  const recording = state === 'recording';
  const working = state === 'transcribing';

  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={working}
      aria-label={LABELS[state]}
      title={LABELS[state]}
      // while recording the button reports the running time to a screen
      // reader; polite so it never interrupts an answer being read out
      aria-live={recording ? 'polite' : 'off'}
      className={`flex min-h-[44px] shrink-0 items-center gap-1.5 rounded-xl px-3 text-sm font-semibold transition-colors ${
        recording
          ? 'bg-red-500/10 text-red-600 dark:bg-red-500/15 dark:text-red-300'
          : state === 'error'
            ? 'text-red-500 hover:bg-red-500/10 dark:text-red-400'
            : 'text-ink-500 hover:bg-ink-100 hover:text-ink-700 disabled:cursor-not-allowed disabled:text-ink-300 dark:text-ink-400 dark:hover:bg-ink-700 dark:hover:text-ink-100 dark:disabled:text-ink-600'
      }`}
    >
      {recording ? (
        <>
          {/* a filled square, the universal stop mark; the pulse is the only
              thing distinguishing an active recording at a glance, so it is
              held still for readers who asked for less motion */}
          <span className="h-3 w-3 shrink-0 rounded-[3px] bg-current motion-safe:animate-pulse" />
          <span className="tabular-nums">{clock(seconds)}</span>
        </>
      ) : working ? (
        <span className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent motion-reduce:animate-none" />
      ) : (
        MicGlyph
      )}
    </button>
  );
}
