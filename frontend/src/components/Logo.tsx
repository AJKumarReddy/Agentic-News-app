/** Wordmark for the app. A newspaper glyph reads as "news" instantly and
 *  stays legible at 20px, which a lettermark in a coloured tile did not. */

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
      {/* folded broadsheet */}
      <path d="M4 6a1.5 1.5 0 0 1 1.5-1.5h9A1.5 1.5 0 0 1 16 6v11.5a2 2 0 0 0 2 2H6.5a2.5 2.5 0 0 1-2.5-2.5V6Z" />
      <path d="M16 9h2.5A1.5 1.5 0 0 1 20 10.5v6.5a2.5 2.5 0 0 1-2.5 2.5" />
      {/* column rules */}
      <path d="M7.5 8h5M7.5 11h5M7.5 14h3" />
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
          <span className="block text-[15px] font-semibold tracking-tight text-white">News AI</span>
          <span className="block text-[11px] text-white/45">Research assistant</span>
        </span>
      )}
    </span>
  );
}
