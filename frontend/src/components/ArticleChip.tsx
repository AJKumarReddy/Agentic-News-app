import { Link } from 'react-router-dom';
import type { ActiveArticle } from '../types';

/**
 * Shows the article a conversation is anchored to, and lets the reader release
 * it.
 *
 * A chat opened from an article keeps answering about it, which is right while
 * the reader is still on that piece and wrong once they have moved on. That
 * state was previously invisible: questions were quietly answered from an
 * article nobody had mentioned in ten turns, and there was no way to tell, let
 * alone stop it.
 */
export default function ArticleChip({
  article,
  onClear,
}: {
  article: ActiveArticle;
  onClear: () => void;
}) {
  return (
    <div className="mb-2 flex items-center gap-1.5 text-[11px]">
      <span className="shrink-0 text-ink-400 dark:text-ink-500">Answering about</span>
      <Link
        to={`/article/${encodeURIComponent(article.article_id)}`}
        className="min-w-0 truncate rounded bg-brand-50 px-1.5 py-0.5 font-medium text-brand-700 hover:underline dark:bg-brand-500/20 dark:text-brand-200"
        title={article.headline || article.article_id}
      >
        {article.headline || article.article_id}
      </Link>
      <button
        type="button"
        onClick={onClear}
        aria-label="Stop answering about this article"
        title="Stop answering about this article"
        className="shrink-0 rounded px-1 py-0.5 text-ink-400 transition hover:bg-ink-100 hover:text-ink-700 dark:text-ink-500 dark:hover:bg-ink-700 dark:hover:text-ink-200"
      >
        ✕
      </button>
    </div>
  );
}
