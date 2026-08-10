import { FormEvent, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import ArticleCard from '../components/ArticleCard';
import { SECTIONS } from '../constants/sections';
import { listSources, searchNews } from '../services/api';
import type { NewsSourceInfo, SearchResponse } from '../types';

export default function SearchPage() {
  // q, section and sources live in the URL (shareable, sidebar links work)
  const [searchParams, setSearchParams] = useSearchParams();
  const section = searchParams.get('section') ?? '';
  const urlQuery = searchParams.get('q') ?? '';
  const activeSources = searchParams.get('sources') ?? '';

  const [queryInput, setQueryInput] = useState(urlQuery);
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [orderBy, setOrderBy] = useState<'newest' | 'oldest' | 'relevance'>('newest');
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [sources, setSources] = useState<NewsSourceInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    listSources()
      .then(setSources)
      .catch(() => setSources([]));
  }, []);

  const runSearch = async (targetPage = 1) => {
    setLoading(true);
    setError('');
    try {
      const data = await searchNews({
        q: urlQuery || undefined,
        section: section || undefined,
        sources: activeSources || undefined,
        from_date: fromDate || undefined,
        to_date: toDate || undefined,
        order_by: orderBy,
        page: targetPage,
        page_size: 12,
      });
      setResult(data);
      setPage(targetPage);
    } catch {
      setError('Search failed. A news API may be unavailable — try again shortly.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setQueryInput(urlQuery);
    runSearch(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams.toString()]);

  const setParams = (next: Record<string, string>) => {
    const params = new URLSearchParams();
    Object.entries(next).forEach(([key, value]) => value && params.set(key, value));
    if (params.toString() === searchParams.toString()) runSearch(1);
    else setSearchParams(params);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setParams({ q: queryInput, section, sources: activeSources });
  };

  const toggleSource = (id: string) => {
    const current = activeSources ? activeSources.split(',') : [];
    const next = current.includes(id) ? current.filter((s) => s !== id) : [...current, id];
    setParams({ q: urlQuery, section, sources: next.join(',') });
  };

  const inputClass =
    'rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm text-ink-800 transition-colors focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100';

  return (
    <div className="h-full overflow-y-auto bg-ink-50">
      <div className="mx-auto max-w-6xl px-4 py-7">
        <h1 className="font-serif text-2xl font-bold text-ink-900">Search the news</h1>
        <p className="mt-1 text-sm text-ink-500">
          Across {sources.length > 0 ? sources.map((s) => s.name).join(' and ') : 'all newsrooms'}
        </p>

        <form onSubmit={submit} className="mt-5 grid grid-cols-2 gap-2.5 md:grid-cols-6">
          <input
            value={queryInput}
            onChange={(e) => setQueryInput(e.target.value)}
            placeholder="Search keywords…"
            className={`col-span-2 ${inputClass}`}
          />
          <select
            value={section}
            onChange={(e) => setParams({ q: urlQuery, section: e.target.value, sources: activeSources })}
            className={inputClass}
          >
            <option value="">All sections</option>
            {SECTIONS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
          <input
            type="date"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
            className={inputClass}
            aria-label="From date"
          />
          <input
            type="date"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
            className={inputClass}
            aria-label="To date"
          />
          <div className="flex gap-2">
            <select
              value={orderBy}
              onChange={(e) => setOrderBy(e.target.value as typeof orderBy)}
              className={`flex-1 ${inputClass}`}
            >
              <option value="newest">Newest</option>
              <option value="oldest">Oldest</option>
              <option value="relevance">Relevance</option>
            </select>
            <button
              type="submit"
              disabled={loading}
              className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-700 disabled:opacity-50"
            >
              Search
            </button>
          </div>
        </form>

        {sources.length > 1 && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-medium uppercase tracking-wider text-ink-400">Sources</span>
            {sources.map((source) => {
              const selected = !activeSources || activeSources.split(',').includes(source.id);
              return (
                <button
                  key={source.id}
                  onClick={() => toggleSource(source.id)}
                  className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                    selected
                      ? 'border-brand-300 bg-brand-50 text-brand-700'
                      : 'border-ink-200 bg-white text-ink-400 hover:border-ink-300'
                  }`}
                >
                  {source.name}
                </button>
              );
            })}
          </div>
        )}

        {error && (
          <div className="mt-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {loading && (
          <div className="mt-7 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="skeleton h-72 rounded-xl" />
            ))}
          </div>
        )}

        {!loading && result && (
          <>
            <div className="mt-6 text-sm text-ink-500">
              {result.articles.length} article{result.articles.length === 1 ? '' : 's'} · page{' '}
              {result.page}
            </div>
            <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {result.articles.map((article) => (
                <ArticleCard key={article.article_id} article={article} />
              ))}
            </div>
            {result.articles.length === 0 && (
              <div className="mt-10 text-center text-sm text-ink-500">
                No articles matched. Try broader keywords or a different section.
              </div>
            )}
            <div className="mt-8 flex items-center justify-center gap-3 pb-10">
              <button
                disabled={page <= 1 || loading}
                onClick={() => runSearch(page - 1)}
                className="rounded-lg border border-ink-200 bg-white px-4 py-2 text-sm font-medium text-ink-700 transition-colors hover:border-ink-300 disabled:opacity-40"
              >
                ← Previous
              </button>
              <button
                disabled={page >= result.pages || loading}
                onClick={() => runSearch(page + 1)}
                className="rounded-lg border border-ink-200 bg-white px-4 py-2 text-sm font-medium text-ink-700 transition-colors hover:border-ink-300 disabled:opacity-40"
              >
                Next →
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
