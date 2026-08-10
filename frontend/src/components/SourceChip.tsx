/** Publisher badge. Keeps newsroom identity visible everywhere an article
 *  appears, so a reader always knows who reported what. */

const STYLES: Record<string, { label: string; className: string }> = {
  guardian: { label: 'Guardian', className: 'bg-[#0b5394]/10 text-[#0b5394]' },
  nyt: { label: 'NY Times', className: 'bg-ink-900/8 text-ink-900' },
  web: { label: 'Web', className: 'bg-warm-100 text-warm-700' },
};

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
  const style = STYLES[key] ?? { label: name || key, className: 'bg-ink-100 text-ink-600' };
  const dims = size === 'xs' ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-0.5 text-[11px]';
  return (
    <span className={`inline-flex shrink-0 items-center rounded font-semibold ${dims} ${style.className}`}>
      {style.label}
    </span>
  );
}
