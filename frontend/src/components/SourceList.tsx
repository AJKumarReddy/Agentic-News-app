import type { Source } from '../types';
import { formatArticleDate } from '../utils/date';

export default function SourceList({ sources }: { sources: Source[] }) {
  if (sources.length === 0) return null;

  const guardianCount = sources.filter((s) => s.type !== 'web').length;
  const webCount = sources.length - guardianCount;

  return (
    <div className="mt-4 border-t border-slate-200 pt-3">
      <div className="mb-2 flex items-baseline gap-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Sources</span>
        {webCount > 0 && (
          <span className="text-[11px] text-slate-400">
            {guardianCount} from The Guardian · {webCount} from the web
          </span>
        )}
      </div>
      <ol className="space-y-2">
        {sources.map((source) => {
          const isWeb = source.type === 'web';
          return (
            <li key={source.n} className="flex gap-2 text-sm">
              <span
                className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded text-[11px] font-bold ${
                  isWeb ? 'bg-amber-100 text-amber-700' : 'bg-guardian-100 text-guardian-700'
                }`}
              >
                {source.n}
              </span>
              <div className="min-w-0">
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`font-medium hover:underline ${
                    isWeb ? 'text-amber-800' : 'text-guardian-700'
                  }`}
                >
                  {source.headline}
                </a>
                <div className="text-xs text-slate-500">
                  {isWeb ? (
                    <span className="rounded bg-amber-50 px-1 py-0.5 font-medium text-amber-700">
                      Web · {source.source || 'external'}
                    </span>
                  ) : (
                    'The Guardian'
                  )}
                  {source.published_at && <> · {formatArticleDate(source.published_at)}</>}
                  {source.author && <> · {source.author}</>}
                  {source.section && <> · {source.section}</>}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
