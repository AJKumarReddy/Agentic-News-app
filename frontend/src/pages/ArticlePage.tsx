import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import ArticleCard from '../components/ArticleCard';
import { getArticleIntelligence } from '../services/api';
import type { ArticleIntelligence } from '../types';
import { formatArticleDate } from '../utils/date';
import SourceChip from '../components/SourceChip';

export default function ArticlePage() {
  // splat param: Guardian IDs like technology/2026/aug/07/story contain slashes
  const params = useParams();
  const articleId = params['*'];
  const navigate = useNavigate();
  const [intelligence, setIntelligence] = useState<ArticleIntelligence | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!articleId) return;
    setLoading(true);
    setError('');
    getArticleIntelligence(decodeURIComponent(articleId))
      .then(setIntelligence)
      .catch(() => setError('Could not load this article. It may not exist or the API is unavailable.'))
      .finally(() => setLoading(false));
  }, [articleId]);

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-8">
        <div className="h-8 w-2/3 skeleton rounded" />
        <div className="mt-4 h-64 skeleton rounded-xl" />
        <div className="mt-4 space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-4 skeleton rounded" />
          ))}
        </div>
        <p className="mt-4 text-sm text-ink-500">Analysing the article…</p>
      </div>
    );
  }

  if (error || !intelligence) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-12 text-center text-ink-600">
        {error || 'Article not found.'}
      </div>
    );
  }

  const { article, analysis, related } = intelligence;
  const published = formatArticleDate(article.published_at, 'full');

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl px-4 py-8">
        <div className="flex flex-wrap items-center gap-2 text-xs text-ink-500">
          <SourceChip sourceId={article.source_id} name={article.source} size="xs" />
          {article.section && (
            <span className="font-medium text-ink-600">
              {article.section}
            </span>
          )}
          {published && <span>{published}</span>}
          {article.author && <span>· {article.author}</span>}
        </div>
        <h1 className="mt-2 font-serif text-3xl font-bold leading-tight text-ink-900">
          {article.headline}
        </h1>
        {article.thumbnail && (
          <img src={article.thumbnail} alt="" className="mt-4 w-full rounded-xl object-cover" />
        )}

        <div className="mt-4 flex flex-wrap gap-2">
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-lg border border-ink-200 px-4 py-2 text-sm font-semibold text-ink-700 hover:bg-ink-50"
          >
            Read the original
          </a>
          <button
            onClick={() =>
              navigate('/', {
                state: {
                  prefill: `Answer questions about this article: "${article.headline}". Start with a brief overview.`,
                  articleId: article.article_id,
                },
              })
            }
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700"
          >
            Ask AI about this article
          </button>
        </div>

        {analysis.summary && (
          <section className="mt-8 rounded-xl border border-ink-200 bg-white p-5 shadow-card">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-500">AI Summary</h2>
            <p className="mt-2 leading-relaxed text-ink-800">{analysis.summary}</p>
          </section>
        )}

        {analysis.key_points.length > 0 && (
          <section className="mt-4 rounded-xl border border-ink-200 bg-white p-5 shadow-card">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-500">Key Points</h2>
            <ul className="mt-2 list-disc space-y-1.5 pl-5 text-ink-800">
              {analysis.key_points.map((point, i) => (
                <li key={i}>{point}</li>
              ))}
            </ul>
          </section>
        )}

        <div className="mt-4 grid gap-4 md:grid-cols-2">
          {analysis.entities.length > 0 && (
            <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-500">Entities</h2>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {analysis.entities.map((entity, i) => (
                  <span key={i} className="rounded-full bg-ink-100 px-2.5 py-1 text-xs text-ink-700">
                    {entity}
                  </span>
                ))}
              </div>
            </section>
          )}
          {analysis.topics.length > 0 && (
            <section className="rounded-xl border border-ink-200 bg-white p-5 shadow-card">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-500">Topics</h2>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {analysis.topics.map((topic, i) => (
                  <span
                    key={i}
                    className="rounded-full bg-brand-50 px-2.5 py-1 text-xs text-brand-700"
                  >
                    {topic}
                  </span>
                ))}
              </div>
            </section>
          )}
        </div>

        {analysis.important_dates.length > 0 && (
          <section className="mt-4 rounded-xl border border-ink-200 bg-white p-5 shadow-card">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-500">
              Important Dates
            </h2>
            <ul className="mt-2 space-y-1.5 text-sm text-ink-800">
              {analysis.important_dates.map((entry, i) => (
                <li key={i}>{entry}</li>
              ))}
            </ul>
          </section>
        )}

        {related.length > 0 && (
          <section className="mt-8 pb-10">
            <h2 className="font-serif text-xl font-bold text-brand-900">Related coverage</h2>
            <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {related.map((r) => (
                <ArticleCard key={r.article_id} article={r} />
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
