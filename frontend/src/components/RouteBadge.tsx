import type { RouteDecision } from '../types';

const ROUTE_LABELS: Record<string, { label: string; className: string; title: string }> = {
  ARTICLE: {
    label: 'Article',
    className: 'bg-brand-50 text-brand-700',
    title: 'Answered from the article you are viewing — no search needed',
  },
  NEWS: {
    label: 'Newsrooms',
    className: 'bg-brand-50 text-brand-700',
    title: 'Answered from indexed newsroom reporting',
  },
  WEB: {
    label: 'Web',
    className: 'bg-warm-50 text-warm-700',
    title: 'Answered from web sources',
  },
  BOTH: {
    label: 'News + Web',
    className: 'bg-accent-50 text-accent-700',
    title: 'Answered from newsroom reporting plus web sources',
  },
};

/** Shows where the routing agent sent this question, and what it understood
 *  the question to be after resolving it against the conversation. */
export default function RouteBadge({ routing }: { routing: RouteDecision }) {
  const route = ROUTE_LABELS[routing.route] ?? ROUTE_LABELS.NEWS;
  const rewritten = routing.standalone_question;

  return (
    <div className="mb-2 flex flex-wrap items-center gap-1.5 text-[11px]">
      <span className={`rounded px-1.5 py-0.5 font-semibold ${route.className}`} title={route.title}>
        {route.label}
      </span>
      {routing.intent && (
        <span className="rounded bg-ink-100 px-1.5 py-0.5 font-medium text-ink-600">
          {routing.intent.toLowerCase().replace('_', ' ')}
        </span>
      )}
      {rewritten && (
        <span
          className="truncate text-ink-400"
          title={`Interpreted as: ${rewritten}`}
        >
          understood as “{rewritten.length > 70 ? `${rewritten.slice(0, 70)}…` : rewritten}”
        </span>
      )}
    </div>
  );
}
