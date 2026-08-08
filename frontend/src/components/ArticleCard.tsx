import { Link, useNavigate } from 'react-router-dom';
import type { Article } from '../types';

export default function ArticleCard({ article }: { article: Article }) {
  const navigate = useNavigate();
  const published = article.published_at
    ? new Date(article.published_at).toLocaleDateString('en-GB', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      })
    : '';

  return (
    <div className="flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm transition-shadow hover:shadow-md">
      {article.thumbnail && (
        <Link to={`/article/${encodeURIComponent(article.article_id)}`}>
          <img src={article.thumbnail} alt="" className="h-40 w-full object-cover" loading="lazy" />
        </Link>
      )}
      <div className="flex flex-1 flex-col p-4">
        <div className="mb-1 flex items-center gap-2 text-xs text-slate-500">
          {article.section && (
            <span className="rounded bg-guardian-50 px-1.5 py-0.5 font-semibold text-guardian-700">
              {article.section}
            </span>
          )}
          {published && <span>{published}</span>}
        </div>
        <Link
          to={`/article/${encodeURIComponent(article.article_id)}`}
          className="font-serif text-base font-bold leading-snug text-slate-900 hover:text-guardian-700"
        >
          {article.headline}
        </Link>
        {article.author && <div className="mt-1 text-xs text-slate-500">{article.author}</div>}
        {article.trail_text && (
          <p className="mt-2 line-clamp-3 text-sm text-slate-600">{article.trail_text}</p>
        )}
        <div className="mt-auto flex gap-2 pt-3">
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
          >
            Read Article
          </a>
          <button
            onClick={() =>
              navigate('/', {
                state: {
                  prefill: `Tell me about this Guardian article: "${article.headline}"`,
                  articleId: article.article_id,
                },
              })
            }
            className="rounded-lg bg-guardian-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-guardian-700"
          >
            Ask AI
          </button>
        </div>
      </div>
    </div>
  );
}
