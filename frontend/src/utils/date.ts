const STYLES: Record<'short' | 'long' | 'full', Intl.DateTimeFormatOptions> = {
  short: { day: 'numeric', month: 'short', year: 'numeric' },
  long: { day: 'numeric', month: 'long', year: 'numeric' },
  full: { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' },
};

/** Format an ISO date for display; safe against null/malformed input. */
export function formatArticleDate(iso: string | null | undefined, style: keyof typeof STYLES = 'long'): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso.slice(0, 10);
  return date.toLocaleDateString('en-GB', STYLES[style]);
}
