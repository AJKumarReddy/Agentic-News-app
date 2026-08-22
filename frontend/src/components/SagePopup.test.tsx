import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/api', () => ({
  getConversation: vi.fn(),
  deleteConversation: vi.fn(async () => undefined),
  fetchSpeech: vi.fn(),
  streamChat: vi.fn(),
}));

import SagePopup from './SagePopup';
import { getConversation } from '../services/api';
import type { ConversationDetail } from '../services/api';

/** A conversation as the backend hands it over. */
function thread(id: string, answer: string): ConversationDetail {
  return {
    id,
    // deliberately not the answer text: these tests assert on what is and is
    // not on screen, and a title echoing it would match either way
    title: `conversation ${id}`,
    messages: [
      { id: 1, role: 'user' as const, content: 'q', sources: [] },
      { id: 2, role: 'assistant' as const, content: answer, sources: [] },
    ],
  };
}

/** Mounts the panel at a location, optionally carrying a handover the way
 *  ChatPage's "Side view" button does. */
function renderPanel(state?: { dockSage: string }) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: '/search', state }]}>
      <SagePopup />
    </MemoryRouter>,
  );
}

describe('Sage side view', () => {
  // jsdom has no layout and so no scrollIntoView; the panel calls it to keep
  // the newest message in view whenever the thread grows.
  beforeAll(() => {
    Element.prototype.scrollIntoView = vi.fn();
  });

  beforeEach(() => {
    localStorage.clear();
    vi.mocked(getConversation).mockReset();
  });

  it('reopens the panel with the thread handed back from the full page', async () => {
    vi.mocked(getConversation).mockResolvedValue(thread('abc', 'carried across'));

    renderPanel({ dockSage: 'abc' });

    expect(await screen.findByText('carried across')).toBeInTheDocument();
    expect(getConversation).toHaveBeenCalledWith('abc');
    // the panel opens itself: a handover the reader has to click open twice is
    // not a return trip
    expect(screen.getByRole('dialog', { name: 'Ask Sage' })).toBeInTheDocument();
  });

  it('shows the thread that was handed over, not the one it last held', async () => {
    // the panel's own stored pointer goes stale the moment the reader opens a
    // different chat from the rail on /chat — the handover is what makes the
    // return leg land on the conversation they were actually reading
    localStorage.setItem('source-sage-conversation', 'stale');
    localStorage.setItem('source-sage-open', 'yes');
    vi.mocked(getConversation).mockImplementation(async (id: string) =>
      id === 'stale' ? thread('stale', 'the old thread') : thread('fresh', 'the one on screen'),
    );

    renderPanel({ dockSage: 'fresh' });

    expect(await screen.findByText('the one on screen')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText('the old thread')).not.toBeInTheDocument());
  });

  it('is not reopened by a slower restore landing after the handover', async () => {
    // a hard load of /chat starts the restore, and Side view can hand over
    // before it lands; the reader's choice must win the race either way
    localStorage.setItem('source-sage-conversation', 'stale');
    let releaseStale: (() => void) | undefined;
    vi.mocked(getConversation).mockImplementation(async (id: string) => {
      if (id === 'stale') {
        await new Promise<void>((resolve) => {
          releaseStale = resolve;
        });
        return thread('stale', 'the old thread');
      }
      return thread('fresh', 'the one on screen');
    });

    renderPanel({ dockSage: 'fresh' });

    expect(await screen.findByText('the one on screen')).toBeInTheDocument();
    releaseStale?.();
    await waitFor(() => expect(screen.queryByText('the old thread')).not.toBeInTheDocument());
    expect(screen.getByText('the one on screen')).toBeInTheDocument();
  });

  it('stays shut when there is no handover and nothing stored', () => {
    renderPanel();

    expect(screen.queryByRole('dialog', { name: 'Ask Sage' })).not.toBeInTheDocument();
    expect(getConversation).not.toHaveBeenCalled();
  });
});
