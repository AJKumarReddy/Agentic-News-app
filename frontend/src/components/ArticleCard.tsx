import { Link, useNavigate } from 'react-router-dom';
import type { Article } from '../types';
import { formatArticleDate } from '../utils/date';
import ArticleImage from './ArticleImage';
import SourceChip from './SourceChip';

export default function ArticleCard({ article }: { article: Article }) {
  const navigate = useNavigate();
  const published = formatArticleDate(article.published_at, 'short');
  const href = `/article/${encodeURIComponent(article.article_id)}`;

  return (
    <article className="group flex flex-col overflow-hidden rounded-xl border border-ink-200 dark:border-ink-700 bg-white dark:bg-ink-800 shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-lift">
      <Link to={href} state={{ article }} className="block overflow-hidden bg-ink-100 dark:bg-ink-700">
        <ArticleImage
          src={article.thumbnail}
          sourceId={article.source_id}
          source={article.source}
          className="h-44 w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
        />
      </Link>

      <div className="flex flex-1 flex-col p-4">
        <div className="mb-2 flex flex-wrap items-center gap-1.5 text-[11px] text-ink-500 dark:text-ink-400">
          <SourceChip sourceId={article.source_id} name={article.source} size="xs" />
          {article.section && <span className="font-medium text-ink-600 dark:text-ink-300">{article.section}</span>}
          {published && <span>· {published}</span>}
        </div>

        <Link
          to={href}
          state={{ article }}
          className="font-serif text-[17px] font-bold leading-snug text-ink-900 dark:text-ink-50 transition-colors group-hover:text-brand-700 dark:group-hover:text-brand-300"
        >
          {article.headline}
        </Link>

        {article.author && <div className="mt-1.5 text-xs text-ink-500 dark:text-ink-400">{article.author}</div>}
        {article.trail_text && (
          <p className="mt-2 line-clamp-3 text-[13px] leading-relaxed text-ink-600 dark:text-ink-300">
            {article.trail_text}
          </p>
        )}

        {/* 44px floor on touch: at py-1.5 these landed around 28px tall, well
            under a comfortable tap target. Back to compact from sm up. */}
        <div className="mt-auto flex gap-2 pt-4">
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-[44px] items-center rounded-lg border border-ink-200 px-4 text-xs font-semibold text-ink-700 transition-colors hover:border-ink-300 hover:bg-ink-50 dark:border-ink-700 dark:text-ink-200 dark:hover:border-ink-500 dark:hover:bg-ink-700 sm:min-h-0 sm:px-3 sm:py-1.5"
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
            className="inline-flex min-h-[44px] items-center rounded-lg bg-brand-600 px-4 text-xs font-semibold text-white transition-colors hover:bg-brand-700 sm:min-h-0 sm:px-3 sm:py-1.5"
          >
            Ask AI
          </button>
        </div>
      </div>
    </article>
  );
}
