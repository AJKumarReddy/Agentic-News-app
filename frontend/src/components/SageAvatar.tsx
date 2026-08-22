/** Sage — the assistant's face.
 *
 *  A 3D render of Sage at her headset, cropped to head-and-shoulders and set
 *  in the brand halo. Shipped from /public rather than drawn as SVG (which is
 *  what this was) because the render's shading is the point — an inline path
 *  cannot carry it, and at ~20KB the file costs one cached request.
 *
 *  The container clips to a circle, so the sliver of laptop in the crop's
 *  bottom corner falls outside the frame. Sizing comes entirely from the
 *  caller's `className`; the image fills whatever box that sets.
 *
 *  Two states, matching the brand sheet:
 *    idle     — the render alone
 *    thinking — three dots over a scrim, the "Sage is researching…" indicator
 *
 *  The dots are sized in percentages so the indicator holds its proportions
 *  from the 18px sidebar mark up to the 64px empty-state one. They animate on
 *  the same `equalize`-style stagger the voice icon uses, and stop entirely
 *  under prefers-reduced-motion (see index.css).
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
    // `block`, not inline-flex: the SVG this replaced was display:block via
    // preflight, and two call sites lean on that — ChatPage centres with
    // mx-auto, MessageBubble toggles `hidden sm:block`. Tailwind emits
    // `hidden` after `block`, so that pair still resolves the way it reads.
    <span
      className={`relative block overflow-hidden rounded-full bg-brand-100 dark:bg-brand-900/60 ${className}`}
      role="img"
      aria-label={state === 'thinking' ? 'Sage is researching' : 'Sage'}
    >
      <img
        src="/sage-avatar.webp"
        alt=""
        aria-hidden="true"
        draggable={false}
        decoding="async"
        className="h-full w-full object-cover"
      />

      {state === 'thinking' && (
        <span className="absolute inset-0 flex items-center justify-center gap-[8%] bg-ink-900/60">
          <span className="h-[15%] w-[15%] animate-sage-dot rounded-full bg-accent-400" />
          <span className="h-[15%] w-[15%] animate-sage-dot rounded-full bg-accent-400 [animation-delay:0.18s]" />
          <span className="h-[15%] w-[15%] animate-sage-dot rounded-full bg-accent-400 [animation-delay:0.36s]" />
        </span>
      )}
    </span>
  );
}
