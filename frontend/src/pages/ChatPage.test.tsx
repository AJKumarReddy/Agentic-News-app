import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/api', () => ({
  getConversation: vi.fn(),
  clearConversationArticle: vi.fn(async () => undefined),
  fetchSpeech: vi.fn(),
  streamChat: vi.fn(),
}));

import ChatPage from './ChatPage';
import { getConversation } from '../services/api';
import type { ConversationDetail } from '../services/api';

const voice = {
  voice: 'off' as const,
  setVoice: vi.fn(),
  available: false,
  nudged: true,
  dismissNudge: vi.fn(),
};

function detail(id: string): ConversationDetail {
  return {
    id,
    title: `conversation ${id}`,
    messages: [
      { id: 1, role: 'user', content: 'what happened today', sources: [] },
      { id: 2, role: 'assistant', content: 'here is the round-up', sources: [] },
    ],
  };
}

/** Reports where "Side view" navigated and what it carried, so the test can
 *  assert on the handover itself rather than on the panel that consumes it. */
function Landed() {
  const { pathname, state } = useLocation();
  return <div data-testid="landed">{pathname + ' ' + JSON.stringify(state)}</div>;
}

function renderChat(entry: string) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/chat" element={<ChatPage voice={voice} />} />
        <Route path="/search" element={<Landed />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('the full chat page', () => {
  beforeAll(() => {
    Element.prototype.scrollIntoView = vi.fn();
  });

  beforeEach(() => {
    localStorage.clear();
    vi.mocked(getConversation).mockReset();
    vi.mocked(getConversation).mockResolvedValue(detail('abc'));
  });

  it('offers a way back to the side panel once there is a thread to carry', async () => {
    renderChat('/chat?conversation=abc');

    expect(await screen.findByRole('button', { name: /side view/i })).toBeInTheDocument();
  });

  it('hands the open thread to the panel on the way out', async () => {
    renderChat('/chat?conversation=abc');

    fireEvent.click(await screen.findByRole('button', { name: /side view/i }));

    // the id travels with the navigation; the stored pointer cannot carry it,
    // because the panel is already mounted and past its one restore
    await waitFor(() =>
      expect(screen.getByTestId('landed')).toHaveTextContent('/search {"dockSage":"abc"}'),
    );
  });

  it('does not offer it on an empty chat, where there is nothing to carry', () => {
    renderChat('/chat');

    expect(screen.queryByRole('button', { name: /side view/i })).not.toBeInTheDocument();
  });
});
