import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import ArticleChip from './ArticleChip';

const ARTICLE = {
  article_id: 'world/2026/aug/01/post-office-inquiry',
  headline: 'Post Office inquiry publishes final report',
};

function renderChip(props: Partial<React.ComponentProps<typeof ArticleChip>> = {}) {
  const onClear = props.onClear ?? vi.fn();
  render(
    <MemoryRouter>
      <ArticleChip article={props.article ?? ARTICLE} onClear={onClear} />
    </MemoryRouter>,
  );
  return { onClear };
}

describe('ArticleChip', () => {
  it('names the article the conversation is anchored to', () => {
    renderChip();
    expect(screen.getByText('Answering about')).toBeInTheDocument();
    expect(screen.getByText(ARTICLE.headline)).toBeInTheDocument();
  });

  it('links to the article itself', () => {
    renderChip();
    expect(screen.getByRole('link', { name: ARTICLE.headline })).toHaveAttribute(
      'href',
      `/article/${encodeURIComponent(ARTICLE.article_id)}`,
    );
  });

  it('lets the reader release the article', () => {
    const { onClear } = renderChip();
    screen.getByRole('button', { name: /stop answering/i }).click();
    expect(onClear).toHaveBeenCalledOnce();
  });

  it('falls back to the id when no headline was stored', () => {
    renderChip({ article: { article_id: ARTICLE.article_id, headline: '' } });
    expect(screen.getByText(ARTICLE.article_id)).toBeInTheDocument();
  });
});
