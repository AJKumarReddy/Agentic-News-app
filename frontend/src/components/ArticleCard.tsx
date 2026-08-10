import { Link, useNavigate } from 'react-router-dom';
import type { Article } from '../types';
import { formatArticleDate } from '../utils/date';
import SourceChip from './SourceChip';

export default function ArticleCard({ article }: { article: Article }) {
  const navigate = useNavigate();
  const published = formatArticleDate(article.published_at, 'short');
  const href = `/article/${encodeURIComponent(article.article_id)}`;
  // tint the accent by publisher so a scan of the grid shows the source mix
  const accentBar =
    article.source_id === 'nyt' ? 'from-accent-400 to-accent-600' : 'from-brand-400 to-brand-600';

  return (
    <article className="group flex flex-col overflow-hidden rounded-xl border border-ink-200 dark:border-ink-700 bg-white dark:bg-ink-800 shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-lift">
      {article.thumbnail ? (
        <Link to={href} state={{ article }} className="block overflow-hidden bg-ink-100 dark:bg-ink-700">
          <img
            src={article.thumbnail}
            alt=""
            className="h-44 w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
            loading="lazy"
          />
        </Link>
      ) : (
        <Link to={href} state={{ article }} className={`block h-1.5 bg-gradient-to-r ${accentBar}`} />
      )}

      <div className="flex flex-1 flex-col p-4">
        <div className="mb-2 flex flex-wrap items-center gap-1.5 text-[11px] text-ink-500 dark:text-ink-400 dark:text-ink-500">
          <SourceChip sourceId={article.source_id} name={article.source} size="xs" />
          {article.section && <span className="font-medium text-ink-600 dark:text-ink-300">{article.section}</span>}
          {published && <span>· {published}</span>}
        </div>

        <Link
          to={href}
          state={{ article }}
          className="font-serif text-[17px] font-bold leading-snug text-ink-900 dark:text-ink-50 transition-colors group-hover:text-brand-700"
        >
          {article.headline}
        </Link>

        {article.author && <div className="mt-1.5 text-xs text-ink-500 dark:text-ink-400 dark:text-ink-500">{article.author}</div>}
        {article.trail_text && (
          <p className="mt-2 line-clamp-3 text-[13px] leading-relaxed text-ink-600 dark:text-ink-300">
            {article.trail_text}
          </p>
        )}

        <div className="mt-auto flex gap-2 pt-4">
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-lg border border-ink-200 dark:border-ink-700 px-3 py-1.5 text-xs font-semibold text-ink-700 dark:text-ink-200 transition-colors hover:border-ink-300 dark:border-ink-600 hover:bg-ink-50 dark:bg-ink-800"
          >
            Read
          </a>
          <button
            onClick={() =>
              navigate('/', {
                state: {
                  prefill: `Tell me about this article: "${article.headline}"`,
                  articleId: article.article_id,
                },
              })
            }
            className="rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-brand-700"
          >
            Ask AI
          </button>
        </div>
      </div>
    </article>
  );
}
