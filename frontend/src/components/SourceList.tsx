import type { Source } from '../types';
import { formatArticleDate } from '../utils/date';

export default function SourceList({ sources }: { sources: Source[] }) {
  if (sources.length === 0) return null;
  return (
    <div className="mt-4 border-t border-slate-200 pt-3">
      <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">Sources</div>
      <ol className="space-y-2">
        {sources.map((source) => (
          <li key={source.n} className="flex gap-2 text-sm">
            <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded bg-guardian-100 text-[11px] font-bold text-guardian-700">
              {source.n}
            </span>
            <div className="min-w-0">
              <a
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="font-medium text-guardian-700 hover:underline"
              >
                {source.headline}
              </a>
              <div className="text-xs text-slate-500">
                The Guardian
                {source.published_at && <> · {formatArticleDate(source.published_at)}</>}
                {source.author && <> · {source.author}</>}
                {source.section && <> · {source.section}</>}
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
