import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/api', () => ({
  searchNews: vi.fn(async () => ({ articles: [], page: 1, pages: 1, total: 0 })),
}));

import SearchPage from './SearchPage';
import { searchNews } from '../services/api';

function renderSearch(url = '/search') {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <SearchPage />
    </MemoryRouter>,
  );
}

/** The refinement controls fold away on a phone (below sm they are `hidden`
 *  until asked for; from sm the grid shows them all). jsdom loads no CSS, so
 *  these assert the state the disclosure publishes rather than the pixels
 *  Tailwind would paint from it. */
describe('search filters on a small screen', () => {
  beforeEach(() => vi.mocked(searchNews).mockClear());

  it('starts folded, so the first article is not pushed off the screen', async () => {
    renderSearch();
    await waitFor(() => expect(searchNews).toHaveBeenCalled());

    expect(screen.getByRole('button', { name: /filters/i })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
  });

  it('opens on demand', async () => {
    renderSearch();
    await waitFor(() => expect(searchNews).toHaveBeenCalled());

    fireEvent.click(screen.getByRole('button', { name: /filters/i }));
    expect(screen.getByRole('button', { name: /filters/i })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
  });

  it('counts what is on, so a folded filter is never a hidden one', async () => {
    // the trap a disclosure sets: results quietly narrowed by a control the
    // reader cannot see. The badge on the toggle is what disarms it.
    renderSearch('/search?section=politics');
    await waitFor(() => expect(searchNews).toHaveBeenCalled());

    expect(screen.getByRole('button', { name: /filters/i })).toHaveTextContent('1');
  });

  it('keeps the query and its button out of the fold', async () => {
    // the two controls every search uses stay on the page at all times
    renderSearch();
    await waitFor(() => expect(searchNews).toHaveBeenCalled());

    expect(screen.getByPlaceholderText(/search keywords/i)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Search' }).length).toBeGreaterThan(0);
  });
});
