import { useId } from 'react';

/** Source wordmark and its "S" swirl.
 *
 *  The mark is one stroked S with round caps — two arcs turning opposite ways,
 *  which is what gives the brand sheet's swirl its motion. Stroked rather than
 *  filled so a single path holds up at the 20px the mobile bar renders it at;
 *  a filled swirl with a tapering tail loses the taper and reads as a blob.
 *
 *  It paints itself in the brand gradient rather than currentColor, because
 *  the sheet's S is the same blue on the white tile and the Midnight one.
 *
 *  The gradient id comes from useId, one per instance. A shared constant id
 *  looked tidier and rendered nothing: the mobile top bar sits before the
 *  desktop rail in the DOM and is display:none above md, so the first
 *  definition of a fixed id lived in a hidden subtree — and a paint server
 *  inside display:none cannot be referenced, so the stroke resolved to
 *  nothing and the mark vanished on exactly the layout most people see.
 */

export function LogoMark({ className = 'h-5 w-5' }: { className?: string }) {
  // useId gives ":r1:" style values; url(#…) is happier without the colons
  const gradientId = `source-mark-${useId().replace(/[^a-zA-Z0-9]/g, '')}`;
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <defs>
        <linearGradient id={gradientId} x1="4" y1="3" x2="20" y2="21" gradientUnits="userSpaceOnUse">
          <stop stopColor="#2563eb" />
          <stop offset="0.55" stopColor="#1d4ed8" />
          <stop offset="1" stopColor="#1e3a8a" />
        </linearGradient>
      </defs>
      {/* the S: upper bowl sweeps one way, lower bowl the other */}
      <path
        d="M16.8 7.6a4.4 4.4 0 1 0-4.8 4.4 4.4 4.4 0 1 1-4.8 4.4"
        stroke={`url(#${gradientId})`}
        strokeWidth="3"
        strokeLinecap="round"
      />
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
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white shadow-sm">
        <LogoMark />
      </span>
      {!compact && (
        <span className="leading-tight">
          <span className="block text-[15px] font-semibold tracking-tight text-white">
            Source
          </span>
          <span className="block text-[11px] font-normal italic text-white/55">
            Ask. Research. Verify.
          </span>
        </span>
      )}
    </span>
  );
}
