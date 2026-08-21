import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { RootRedirect } from './App';

/** Reports where the redirect landed, so these tests assert on the resulting
 *  URL rather than on whichever page happens to render there. Mounting the
 *  real App would drag in the sidebar and both pages, and their fetches, to
 *  test four lines of routing. */
function Landed() {
  const { pathname, search } = useLocation();
  return <div data-testid="landed">{pathname + search}</div>;
}

function renderAt(entry: string) {
  render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/" element={<RootRedirect />} />
        <Route path="/search" element={<Landed />} />
        <Route path="/chat" element={<Landed />} />
      </Routes>
    </MemoryRouter>,
  );
  return screen.getByTestId('landed').textContent;
}

describe('the site root', () => {
  it('opens the news rather than an empty chat', () => {
    expect(renderAt('/')).toBe('/search');
  });

  it('keeps section links working through the redirect', () => {
    // a sidebar section link is /search?section=... — it must not be
    // swallowed by the root rule on the way past
    expect(renderAt('/search?section=technology')).toBe('/search?section=technology');
  });

  it('forwards chat links minted before the move', () => {
    // every "recent chat" link used to look like this, and they may be
    // bookmarked; dropping the conversation would silently open a blank chat
    expect(renderAt('/?conversation=abc123')).toBe('/chat?conversation=abc123');
  });
});
