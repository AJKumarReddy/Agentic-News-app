import { FormEvent, useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import ArticleCard from '../components/ArticleCard';
import { searchNews } from '../services/api';
import type { SearchResponse } from '../types';

const SECTIONS = ['', 'technology', 'politics', 'business', 'world', 'environment', 'science', 'media'];

export default function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState(searchParams.get('q') ?? '');
  const [section, setSection] = useState(searchParams.get('section') ?? '');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [orderBy, setOrderBy] = useState<'newest' | 'oldest' | 'relevance'>('newest');
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const runSearch = useCallback(
    async (targetPage = 1) => {
      setLoading(true);
      setError('');
      try {
        const data = await searchNews({
          q: query || undefined,
          section: section || undefined,
          from_date: fromDate || undefined,
          to_date: toDate || undefined,
          order_by: orderBy,
          page: targetPage,
          page_size: 12,
        });
        setResult(data);
        setPage(targetPage);
      } catch {
        setError('Search failed. The Guardian API may be unavailable — try again shortly.');
      } finally {
        setLoading(false);
      }
    },
    [query, section, fromDate, toDate, orderBy],
  );

  // Run once on mount / when arriving with ?section=…
  useEffect(() => {
    const urlSection = searchParams.get('section') ?? '';
    setSection(urlSection);
    runSearch(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams.get('section')]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSearchParams(query ? { q: query, ...(section ? { section } : {}) } : section ? { section } : {});
    runSearch(1);
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl px-4 py-6">
        <h1 className="font-serif text-2xl font-bold text-guardian-900">Search Guardian News</h1>

        <form onSubmit={submit} className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-6">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search keywords…"
            className="col-span-2 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-guardian-500 focus:outline-none md:col-span-2"
          />
          <select
            value={section}
            onChange={(e) => setSection(e.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            {SECTIONS.map((s) => (
              <option key={s} value={s}>
                {s ? s[0].toUpperCase() + s.slice(1) : 'All sections'}
              </option>
            ))}
          </select>
          <input
            type="date"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            aria-label="From date"
          />
          <input
            type="date"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            aria-label="To date"
          />
          <div className="flex gap-2">
            <select
              value={orderBy}
              onChange={(e) => setOrderBy(e.target.value as typeof orderBy)}
              className="flex-1 rounded-lg border border-slate-300 px-2 py-2 text-sm"
            >
              <option value="newest">Newest</option>
              <option value="oldest">Oldest</option>
              <option value="relevance">Relevance</option>
            </select>
            <button
              type="submit"
              disabled={loading}
              className="rounded-lg bg-guardian-600 px-4 py-2 text-sm font-semibold text-white hover:bg-guardian-700 disabled:opacity-50"
            >
              Search
            </button>
          </div>
        </form>

        {error && (
          <div className="mt-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {loading && (
          <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-64 animate-pulse rounded-xl bg-slate-200" />
            ))}
          </div>
        )}

        {!loading && result && (
          <>
            <div className="mt-4 text-sm text-slate-500">
              {result.total.toLocaleString()} articles · page {result.page} of {result.pages}
            </div>
            <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {result.articles.map((article) => (
                <ArticleCard key={article.article_id} article={article} />
              ))}
            </div>
            <div className="mt-6 flex items-center justify-center gap-3 pb-8">
              <button
                disabled={page <= 1 || loading}
                onClick={() => runSearch(page - 1)}
                className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium disabled:opacity-40"
              >
                ← Previous
              </button>
              <button
                disabled={page >= result.pages || loading}
                onClick={() => runSearch(page + 1)}
                className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium disabled:opacity-40"
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
