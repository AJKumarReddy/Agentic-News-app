import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import SourceList from './SourceList';
import type { Source } from '../types';

const SOURCES: Source[] = [
  {
    n: 1,
    article_id: 'technology/2026/aug/07/a',
    headline: 'OpenAI announces new model',
    url: 'https://www.theguardian.com/technology/2026/aug/07/a',
    published_at: '2026-08-07T10:00:00Z',
    section: 'Technology',
    author: 'Jane Reporter',
    type: 'publisher',
    source_id: 'guardian',
    source: 'The Guardian',
  },
  {
    n: 2,
    article_id: 'business/2026/aug/05/b',
    headline: 'Markets react to AI news',
    url: 'https://www.theguardian.com/business/2026/aug/05/b',
    published_at: '2026-08-05T09:00:00Z',
    section: 'Business',
    author: '',
    type: 'publisher',
    source_id: 'nyt',
    source: 'The New York Times',
  },
];

describe('SourceList', () => {
  it('renders nothing when there are no sources', () => {
    const { container } = render(<SourceList sources={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders numbered citations linking to Guardian URLs', () => {
    render(<SourceList sources={SOURCES} />);
    expect(screen.getByText('Sources')).toBeInTheDocument();
    const link = screen.getByRole('link', { name: 'OpenAI announces new model' });
    expect(link).toHaveAttribute('href', 'https://www.theguardian.com/technology/2026/aug/07/a');
    expect(link).toHaveAttribute('target', '_blank');
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('shows author metadata', () => {
    render(<SourceList sources={SOURCES} />);
    expect(screen.getByText(/Jane Reporter/)).toBeInTheDocument();
  });

  it('labels each source with its publisher', () => {
    render(<SourceList sources={SOURCES} />);
    // a reader must be able to tell which newsroom reported which claim
    expect(screen.getByText('Guardian')).toBeInTheDocument();
    expect(screen.getByText('NY Times')).toBeInTheDocument();
  });
});
