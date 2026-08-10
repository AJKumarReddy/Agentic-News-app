import type { RouteDecision } from '../types';

const ROUTE_LABELS: Record<string, { label: string; className: string; title: string }> = {
  ARTICLE: {
    label: 'Article',
    className: 'bg-brand-50 text-brand-700',
    title: 'Answered from the article you are viewing — no search needed',
  },
  NEWS: {
    label: 'Guardian',
    className: 'bg-brand-50 text-brand-700',
    title: 'Answered from Guardian reporting',
  },
  WEB: {
    label: 'Web',
    className: 'bg-amber-50 text-amber-700',
    title: 'Answered from web sources',
  },
  BOTH: {
    label: 'Guardian + Web',
    className: 'bg-emerald-50 text-emerald-700',
    title: 'Answered from Guardian reporting plus web sources',
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
        <span className="rounded bg-slate-100 px-1.5 py-0.5 font-medium text-slate-600">
          {routing.intent.toLowerCase().replace('_', ' ')}
        </span>
      )}
      {rewritten && (
        <span
          className="truncate text-slate-400"
          title={`Interpreted as: ${rewritten}`}
        >
          understood as “{rewritten.length > 70 ? `${rewritten.slice(0, 70)}…` : rewritten}”
        </span>
      )}
    </div>
  );
}
