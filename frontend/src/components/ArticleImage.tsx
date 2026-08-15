/** Article artwork with a publisher-branded filler.
 *
 *  Not every article comes with usable art — NYT in particular omits
 *  multimedia on wire briefs, corrections and newsletters, and its image CDN
 *  occasionally 404s an older crop. A ragged grid where some cards have a
 *  picture and others collapse to a hairline reads as broken, so anything
 *  without a loadable image gets a masthead-styled placeholder in the same
 *  slot and the layout stays even.
 */

import { useEffect, useState } from 'react';

const FILLERS: Record<string, { label: string; className: string }> = {
  nyt: {
    label: 'The New York Times',
    // NYT house style: black masthead on newsprint
    className: 'bg-ink-900 text-white/90 dark:bg-ink-900',
  },
  guardian: {
    label: 'The Guardian',
    className: 'bg-[#0b5394] text-white/90',
  },
};

export default function ArticleImage({
  src,
  sourceId,
  source,
  className,
}: {
  src?: string;
  sourceId?: string;
  source?: string;
  className: string;
}) {
  const [failed, setFailed] = useState(false);

  // a new article in the same card slot deserves a fresh attempt
  useEffect(() => setFailed(false), [src]);

  if (src && !failed) {
    return (
      <img
        src={src}
        alt=""
        className={className}
        loading="lazy"
        onError={() => setFailed(true)}
      />
    );
  }

  const filler = FILLERS[sourceId ?? ''] ?? {
    label: source || 'News',
    className: 'bg-ink-700 text-white/90',
  };

  return (
    <div
      className={`flex items-center justify-center overflow-hidden ${filler.className} ${className}`}
      aria-hidden="true"
    >
      <span className="px-4 text-center font-serif text-base font-bold leading-tight tracking-tight sm:text-lg">
        {filler.label}
      </span>
    </div>
  );
}
