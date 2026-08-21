/** Wordmark for the app: a lens over column rules.
 *
 *  Both halves of the name in one shape — the circle reads as a lens, the
 *  ruled lines inside it as newsprint. Kept to a single stroked path set for
 *  the same reason the previous broadsheet glyph was: two overlapping shapes
 *  (a loupe laid across a newspaper) turn to mush at the 20px the mobile bar
 *  renders it at.
 *
 *  Two rules, not three, and of different lengths. Three at this diameter
 *  merged into a single bar at 20px and the whole mark read as a browser
 *  zoom-out button; equal-length rules read as an equals sign. Ragged lengths
 *  with a wide gap are what make it read as a column of type.
 */

export function LogoMark({ className = 'h-5 w-5' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {/* lens */}
      <circle cx="9.5" cy="9.5" r="7.5" />
      {/* two ragged column rules, spaced far enough to survive 20px */}
      <path d="M6 7.5h8M6 11h5.5" />
      {/* handle, leaving the rim on the 45° diagonal */}
      <path d="M15 15l5.5 5.5" />
    </svg>
  );
}

export default function Logo({
  compact = false,
  className = '',
}: {
  compact?: boolean;
  className?: string;
}) {
  return (
    <span className={`flex items-center gap-2.5 ${className}`}>
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-white/15 bg-white/[0.07] text-white">
        <LogoMark />
      </span>
      {!compact && (
        <span className="leading-tight">
          <span className="block text-[15px] font-semibold tracking-tight text-white">NewsLens</span>
          <span className="block text-[11px] text-white/45">See beyond the headlines.</span>
        </span>
      )}
    </span>
  );
}
