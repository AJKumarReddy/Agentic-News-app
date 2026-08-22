/** Sage — the assistant's face.
 *
 *  A Midnight visor inside a light helmet, with ear cups either side and two
 *  arced eyes. Drawn rather than shipped as an image so it inherits the page's
 *  scale crisply and costs no request, and so the `thinking` state can just
 *  swap what is on the visor instead of loading a second asset.
 *
 *  Two states, matching the brand sheet:
 *    idle     — curved eyes, the resting face
 *    thinking — three dots, the "Sage is researching…" indicator
 *
 *  The dots animate on the same `equalize`-style stagger the voice icon uses,
 *  and stop entirely under prefers-reduced-motion (see index.css).
 */

export type SageState = 'idle' | 'thinking';

export default function SageAvatar({
  state = 'idle',
  className = 'h-8 w-8',
}: {
  state?: SageState;
  className?: string;
}) {
  return (
    <svg viewBox="0 0 40 40" fill="none" className={className} role="img" aria-label="Sage">
      {/* halo — the glow the sheet sets the face against */}
      <circle cx="20" cy="20" r="19" className="fill-brand-100 dark:fill-brand-900/60" />

      {/* ear cups */}
      <rect x="3" y="15" width="6" height="11" rx="3" className="fill-brand-500" />
      <rect x="31" y="15" width="6" height="11" rx="3" className="fill-brand-500" />

      {/* helmet, then the visor it holds */}
      <rect x="7" y="7" width="26" height="26" rx="10" className="fill-white dark:fill-ink-200" />
      <rect x="10" y="10" width="20" height="19" rx="7.5" className="fill-ink-900" />

      {state === 'idle' ? (
        // eyes: arcs opening downward, which is what reads as a smile rather
        // than as two neutral slits
        <path
          d="M14.6 18.4c.7 1.6 2.4 1.6 3.1 0M22.3 18.4c.7 1.6 2.4 1.6 3.1 0"
          className="stroke-accent-400"
          strokeWidth="2.1"
          strokeLinecap="round"
        />
      ) : (
        <g className="fill-accent-400">
          <circle cx="15" cy="19.5" r="1.7" className="animate-sage-dot" />
          <circle cx="20" cy="19.5" r="1.7" className="animate-sage-dot [animation-delay:0.18s]" />
          <circle cx="25" cy="19.5" r="1.7" className="animate-sage-dot [animation-delay:0.36s]" />
        </g>
      )}
    </svg>
  );
}
