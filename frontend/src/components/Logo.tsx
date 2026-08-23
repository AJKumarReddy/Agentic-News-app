/** Source wordmark and its "S" mark.
 *
 *  The mark is the 3D S under a magnifier, shipped from /public. It carries a
 *  white ground of its own, so it reads as a tile wherever it lands — which is
 *  the point on the rail and the mobile bar, where it sits on Midnight. The
 *  earlier cut of this art came on that dark ground instead and dissolved into
 *  those surfaces; nothing is drawn behind it either way.
 *
 *  Corners round in percent rather than at a fixed radius: the mark renders at
 *  32px in the rail and 20px in the mobile bar, and one `rounded-lg` that
 *  looks right at 32 reads as a chamfer at 20.
 *
 *  The stroked SVG this replaced needed a per-instance gradient id, because a
 *  shared one resolved to nothing in the mobile bar — that subtree is
 *  display:none above md and comes first in the DOM, and a paint server inside
 *  display:none cannot be referenced. A raster has no paint server, so the
 *  useId workaround went with it.
 */

export function LogoMark({ className = 'h-5 w-5' }: { className?: string }) {
  return (
    <img
      src="/source-icon.webp"
      alt=""
      aria-hidden="true"
      draggable={false}
      decoding="async"
      className={`shrink-0 rounded-[22%] object-cover ${className}`}
    />
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
      <LogoMark className="h-8 w-8 shadow-sm" />
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
