import type { RouteDecision } from '../types';

const ROUTE_LABELS: Record<string, { label: string; className: string; title: string }> = {
  ARTICLE: {
    label: 'Article',
    className: 'bg-brand-50 text-brand-700 dark:bg-brand-500/20 dark:text-brand-200',
    title: 'Answered from the article you are viewing — no search needed',
  },
  NEWS: {
    label: 'Newsrooms',
    className: 'bg-brand-50 text-brand-700 dark:bg-brand-500/20 dark:text-brand-200',
    title: 'Answered from indexed newsroom reporting',
  },
  WEB: {
    label: 'Web',
    className: 'bg-warm-50 text-warm-700 dark:bg-warm-500/20 dark:text-warm-200',
    title: 'Answered from web sources',
  },
  BOTH: {
    label: 'News + Web',
    className: 'bg-accent-50 text-accent-700 dark:bg-accent-500/20 dark:text-accent-200',
    title: 'Answered from newsroom reporting plus web sources',
  },
  DECLINE: {
    label: 'Out of scope',
    className: 'bg-ink-100 text-ink-600 dark:bg-ink-700 dark:text-ink-300',
    title: 'Not a news question — nothing was searched',
  },
};

/** Shows where the routing agent sent this question, and what it understood
 *  the question to be after resolving it against the conversation. */
export default function RouteBadge({ routing }: { routing: RouteDecision }) {
  const route = ROUTE_LABELS[routing.route] ?? ROUTE_LABELS.NEWS;
  // A declined turn was never interpreted as a question or given an intent —
  // showing either would suggest the assistant took the request seriously.
  const declined = routing.route === 'DECLINE';
  const rewritten = declined ? '' : routing.standalone_question;

  return (
    <div className="mb-2 flex flex-wrap items-center gap-1.5 text-[11px]">
      <span className={`rounded px-1.5 py-0.5 font-semibold ${route.className}`} title={route.title}>
        {route.label}
      </span>
      {!declined && routing.intent && (
        <span className="rounded bg-ink-100 dark:bg-ink-700 px-1.5 py-0.5 font-medium text-ink-600 dark:text-ink-300">
          {routing.intent.toLowerCase().replace('_', ' ')}
        </span>
      )}
      {rewritten && (
        <span
          className="truncate text-ink-400 dark:text-ink-500"
          title={`Interpreted as: ${rewritten}`}
        >
          understood as “{rewritten.length > 70 ? `${rewritten.slice(0, 70)}…` : rewritten}”
        </span>
      )}
    </div>
  );
}
