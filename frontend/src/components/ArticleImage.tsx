/** Article artwork over a publisher-branded filler.
 *
 *  Not every article comes with usable art — NYT omits multimedia on wire
 *  briefs, corrections and newsletters, and relayed articles point at whatever
 *  CDN the original outlet uses, which is often slow and sometimes gone. A
 *  ragged grid where some cards have a picture and others collapse to a
 *  hairline reads as broken, so every slot is filled.
 *
 *  The filler is painted *underneath* rather than swapped in on failure. The
 *  old version rendered the `<img>` alone and only fell back in `onError`,
 *  which left a bare grey box for the whole of a slow third-party fetch and
 *  forever for an image that stalls without ever erroring. Now the branded
 *  panel is there from the first paint and the photograph fades over it when
 *  it actually arrives — so a card is never empty, only less specific.
 */

import { useEffect, useState } from 'react';
import { publisherName } from '../utils/publisher';

const FILLERS: Record<string, { label: string; className: string }> = {
  nyt: {
    label: 'The New York Times',
    // NYT house style: black masthead on newsprint
    className: 'bg-ink-900 text-white/90',
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
  const [loaded, setLoaded] = useState(false);

  // a new article in the same card slot deserves a fresh attempt
  useEffect(() => {
    setFailed(false);
    setLoaded(false);
  }, [src]);

  // relayed articles carry their own publisher, so the generic branch names
  // the outlet that reported it rather than saying "News"
  const filler = FILLERS[sourceId ?? ''] ?? {
    label: publisherName(source) || 'News',
    className: 'bg-ink-700 text-white/90',
  };

  return (
    <div className={`relative overflow-hidden ${className}`}>
      <div
        className={`absolute inset-0 flex items-center justify-center ${filler.className}`}
        aria-hidden="true"
      >
        <span className="px-4 text-center font-serif text-base font-bold leading-tight tracking-tight sm:text-lg">
          {filler.label}
        </span>
      </div>

      {src && !failed && (
        <img
          src={src}
          alt=""
          loading="lazy"
          onLoad={() => setLoaded(true)}
          onError={() => setFailed(true)}
          className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-300 ${
            loaded ? 'opacity-100' : 'opacity-0'
          }`}
        />
      )}
    </div>
  );
}
