import type { Source } from '../types';
import { formatArticleDate } from '../utils/date';
import SourceChip from './SourceChip';

export default function SourceList({ sources }: { sources: Source[] }) {
  if (sources.length === 0) return null;

  const webCount = sources.filter((s) => s.type === 'web').length;
  const newsCount = sources.length - webCount;

  return (
    <div className="mt-5 border-t border-ink-200 dark:border-ink-700 pt-3">
      <div className="mb-2.5 flex items-baseline gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-500 dark:text-ink-400 dark:text-ink-500">Sources</span>
        <span className="text-[11px] text-ink-400 dark:text-ink-500">
          {newsCount > 0 && `${newsCount} from newsrooms`}
          {newsCount > 0 && webCount > 0 && ' · '}
          {webCount > 0 && `${webCount} from the web`}
        </span>
      </div>
      <ol className="space-y-2.5">
        {sources.map((source) => {
          const isWeb = source.type === 'web';
          return (
            <li key={source.n} className="flex gap-2.5 text-sm">
              <span
                className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded text-[11px] font-bold ${
                  isWeb ? 'bg-warm-100 text-warm-700 dark:bg-warm-500/20 dark:text-warm-200' : 'bg-brand-100 text-brand-700 dark:bg-brand-500/20 dark:text-brand-200'
                }`}
              >
                {source.n}
              </span>
              <div className="min-w-0">
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium text-ink-800 dark:text-ink-100 underline-offset-2 hover:text-brand-700 hover:underline"
                >
                  {source.headline}
                </a>
                <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-ink-500 dark:text-ink-400 dark:text-ink-500">
                  <SourceChip
                    sourceId={isWeb ? 'web' : source.source_id}
                    name={source.source}
                    size="xs"
                  />
                  {isWeb ? <span>{source.source}</span> : source.source && <span>{source.source}</span>}
                  {source.published_at && <span>· {formatArticleDate(source.published_at)}</span>}
                  {source.author && <span>· {source.author}</span>}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
