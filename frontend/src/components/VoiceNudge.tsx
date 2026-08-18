import VoiceIcon from './VoiceIcon';

/**
 * A one-time offer of voice playback.
 *
 * Shown once, after the reader's first answer, and only while they have never
 * expressed a preference either way. Accepting or dismissing settles it for
 * good — a suggestion that comes back is a nag.
 */
export default function VoiceNudge({
  onEnable,
  onDismiss,
}: {
  onEnable: () => void;
  onDismiss: () => void;
}) {
  return (
    <div className="mb-2 flex animate-fade-up items-center gap-2 rounded-lg border border-accent-200 bg-accent-50 px-3 py-2 text-[13px] dark:border-accent-500/30 dark:bg-accent-500/10">
      <VoiceIcon state="speaking" className="h-3.5 w-3.5 shrink-0 text-accent-600 dark:text-accent-300" />
      <span className="min-w-0 flex-1 text-accent-800 dark:text-accent-100">
        Listen to answers instead of reading them?
      </span>
      <button
        onClick={onEnable}
        className="shrink-0 rounded-md bg-accent-600 px-2.5 py-1 text-[12px] font-semibold text-white transition-colors hover:bg-accent-700"
      >
        Turn on
      </button>
      <button
        onClick={onDismiss}
        aria-label="Dismiss"
        className="shrink-0 rounded p-1 text-accent-700/60 transition-colors hover:text-accent-900 dark:text-accent-200/60 dark:hover:text-accent-100"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <path d="M6 6l12 12M18 6L6 18" />
        </svg>
      </button>
    </div>
  );
}
