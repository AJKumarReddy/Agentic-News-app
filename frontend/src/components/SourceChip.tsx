/** Publisher badge. Keeps newsroom identity visible everywhere an article
 *  appears, so a reader always knows who reported what. */
import { publisherName } from '../utils/publisher';

/** Our own three sources, which have real identities worth spending a brand
 *  colour on. Everything else is relayed and comes from the palette below. */
const PINNED: Record<string, { label: string; className: string }> = {
  guardian: { label: 'Guardian', className: 'bg-[#0b5394]/10 text-[#0b5394] dark:bg-[#4a9de0]/15 dark:text-[#7ab8ea]' },
  nyt: { label: 'NY Times', className: 'bg-ink-900/8 text-ink-900 dark:bg-white/10 dark:text-ink-100' },
  web: { label: 'Web', className: 'bg-warm-100 text-warm-700 dark:bg-warm-500/20 dark:text-warm-200' },
};

/** The aggregator relays hundreds of newsrooms, so a colour per publisher
 *  cannot be maintained by hand — and leaving them all on one grey (or all on
 *  brand blue) makes a mixed result list read as a single undifferentiated
 *  source. Instead each publisher is hashed onto a fixed palette: the mapping
 *  needs no upkeep, and a given newsroom keeps the same colour everywhere it
 *  appears, which is the property that actually helps someone scanning a page.
 *
 *  Eight tones means popular publishers will occasionally collide. That is
 *  acceptable because the chip also spells the name out — colour is the second
 *  cue here, not the only one.
 *
 *  Written as whole class strings because Tailwind scans source statically;
 *  a `bg-${hue}-100` built at runtime would never be compiled.
 */
const PALETTE = [
  'bg-slate-100 text-slate-700 dark:bg-slate-400/15 dark:text-slate-300',
  'bg-cyan-50 text-cyan-800 dark:bg-cyan-400/15 dark:text-cyan-300',
  'bg-stone-100 text-stone-700 dark:bg-stone-400/15 dark:text-stone-300',
  'bg-emerald-50 text-emerald-800 dark:bg-emerald-400/15 dark:text-emerald-300',
  'bg-orange-50 text-orange-800 dark:bg-orange-400/15 dark:text-orange-300',
  'bg-blue-50 text-blue-800 dark:bg-blue-400/15 dark:text-blue-300',
  'bg-purple-50 text-purple-800 dark:bg-purple-400/15 dark:text-purple-300',
  'bg-red-50 text-red-800 dark:bg-red-400/15 dark:text-red-300',
];

/** FNV-1a. Any stable hash would do; this one is short and has no deps. */
function paletteFor(identity: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < identity.length; i += 1) {
    hash ^= identity.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return PALETTE[Math.abs(hash) % PALETTE.length];
}

export default function SourceChip({
  sourceId,
  name,
  size = 'sm',
}: {
  sourceId?: string;
  name?: string;
  size?: 'xs' | 'sm';
}) {
  const key = sourceId || 'guardian';
  const pinned = PINNED[key];
  // Hash the publisher, never the source id: every relayed article shares the
  // id "thenewsapi", so keying on it would paint all of them one colour.
  const label = pinned?.label ?? (publisherName(name) || key);
  const className = pinned?.className ?? paletteFor(label.toLowerCase());
  const dims = size === 'xs' ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-0.5 text-[11px]';
  return (
    <span className={`inline-flex shrink-0 items-center rounded font-semibold ${dims} ${className}`}>
      {label}
    </span>
  );
}
