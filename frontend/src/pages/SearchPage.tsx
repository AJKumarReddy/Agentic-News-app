import { FormEvent, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import ArticleCard from '../components/ArticleCard';
import { SECTIONS } from '../constants/sections';
import { searchNews } from '../services/api';
import type { SearchResponse } from '../types';

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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

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
        page_size: 24,
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

  // text-base below sm keeps mobile browsers from zooming in on focus; the
  // 44px floor is the tap target, dropped from sm where a pointer is precise
  const inputClass =
    'min-h-[44px] w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-base text-ink-800 transition-colors focus:border-accent-400 focus:outline-none focus:ring-2 focus:ring-accent-100 dark:border-ink-700 dark:bg-ink-800 dark:text-ink-100 dark:focus:ring-accent-500/20 sm:min-h-0 sm:text-sm';

  return (
    <div className="h-full overflow-y-auto overscroll-contain bg-brand-soft dark:bg-brand-soft-dark">
      <div className="mx-auto max-w-[104rem] px-4 py-6 sm:py-7">
        <h1 className="font-serif text-2xl font-bold text-ink-900 dark:text-ink-50">
          Research the news
        </h1>
        {/* no longer lists the publishers: that enumeration went stale every
            time a key was added or removed, and the promise that matters is
            the link back to the original, not the roster */}
        <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
          Search across trusted newsrooms — every result links back to the original report.
        </p>

        {/* one column on a phone — two native date pickers side by side at
            ~165px each clip their own controls in mobile Chrome */}
        <form onSubmit={submit} className="mt-5 grid grid-cols-1 gap-2.5 sm:grid-cols-2 md:grid-cols-7">
          <input
            value={queryInput}
            onChange={(e) => setQueryInput(e.target.value)}
            placeholder="Search keywords…"
            type="search"
            enterKeyHint="search"
            className={`sm:col-span-2 ${inputClass}`}
          />
          <select
            value={section}
            onChange={(e) => setParams({ q: urlQuery, section: e.target.value, sources: activeSources })}
            className={inputClass}
            aria-label="Section"
          >
            <option value="">All sections</option>
            {SECTIONS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
          {/* stacked below sm: a native date control needs more than the ~160px
              a half-width column gives it at 360px, and clips its own icon.
              `contents` puts both back as direct grid cells from sm up. */}
          <div className="grid grid-cols-1 gap-2.5 sm:contents">
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
          </div>
          <div className="flex gap-2 md:col-span-2">
            <select
              value={orderBy}
              onChange={(e) => setOrderBy(e.target.value as typeof orderBy)}
              className={`flex-1 ${inputClass}`}
              aria-label="Sort order"
            >
              <option value="newest">Newest</option>
              <option value="oldest">Oldest</option>
              <option value="relevance">Relevance</option>
            </select>
            <button
              type="submit"
              disabled={loading}
              className="min-h-[44px] shrink-0 rounded-lg bg-brand-600 px-5 text-sm font-semibold text-white transition-colors hover:bg-brand-700 disabled:opacity-50 sm:min-h-0 sm:px-4 sm:py-2"
            >
              Search
            </button>
          </div>
        </form>

        {error && (
          <div className="mt-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
            {error}
          </div>
        )}

        {loading && (
          <div className="mt-7 grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(min(17rem,100%),1fr))]">
            {Array.from({ length: 12 }).map((_, i) => (
              <div key={i} className="skeleton h-72 rounded-xl" />
            ))}
          </div>
        )}

        {!loading && result && (
          <>
            <div className="mt-6 grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(min(17rem,100%),1fr))]">
              {result.articles.map((article) => (
                <ArticleCard key={article.article_id} article={article} />
              ))}
            </div>
            {result.articles.length === 0 && (
              <div className="mt-10 text-center text-sm text-ink-500 dark:text-ink-400">
                No articles matched. Try broader keywords or a different section.
              </div>
            )}
            <div className="mt-8 flex items-center justify-center gap-3 pb-[max(2.5rem,env(safe-area-inset-bottom))]">
              <button
                disabled={page <= 1 || loading}
                onClick={() => runSearch(page - 1)}
                className="inline-flex min-h-[44px] items-center rounded-lg border border-ink-200 bg-white px-4 text-sm font-medium text-ink-700 transition-colors hover:border-ink-300 disabled:opacity-40 dark:border-ink-700 dark:bg-ink-800 dark:text-ink-200 dark:hover:border-ink-500"
              >
                ← Previous
              </button>
              {/* between the controls that change it, rather than in a status
                  line at the top of the page nowhere near them */}
              <span
                aria-live="polite"
                className="min-w-[6.5rem] text-center text-sm tabular-nums text-ink-500 dark:text-ink-400"
              >
                Page {result.page}
                {result.pages > 1 && <span className="text-ink-400 dark:text-ink-500"> of {result.pages}</span>}
              </span>
              <button
                disabled={page >= result.pages || loading}
                onClick={() => runSearch(page + 1)}
                className="inline-flex min-h-[44px] items-center rounded-lg border border-ink-200 bg-white px-4 text-sm font-medium text-ink-700 transition-colors hover:border-ink-300 disabled:opacity-40 dark:border-ink-700 dark:bg-ink-800 dark:text-ink-200 dark:hover:border-ink-500"
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
