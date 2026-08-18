import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import MessageBubble from './MessageBubble';
import type { ChatMessage, SpeechState } from '../types';

const answer: ChatMessage = {
  id: 7,
  role: 'assistant',
  content: 'The FTSE 100 is an index of large companies listed in London.',
  sources: [],
};

describe('MessageBubble playback control', () => {
  it('writes the control name on the button rather than hiding it in a tooltip', () => {
    render(<MessageBubble message={answer} onSpeak={() => {}} />);
    expect(screen.getByRole('button', { name: 'Read aloud' })).toBeInTheDocument();
  });

  it.each<[SpeechState, string]>([
    ['idle', 'Read aloud'],
    ['loading', 'Preparing…'],
    ['speaking', 'Stop reading'],
    ['error', 'Audio unavailable'],
  ])('names the %s state on the button face', (state, label) => {
    render(<MessageBubble message={answer} speechState={state} onSpeak={() => {}} />);
    expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
  });

  it('takes its accessible name from the visible text, so speech control can match it', () => {
    // a divergent aria-label is what "label in name" forbids: a reader saying
    // the words they can see must reach the same button
    render(<MessageBubble message={answer} onSpeak={() => {}} />);
    const button = screen.getByRole('button', { name: 'Read aloud' });
    expect(button).not.toHaveAttribute('aria-label');
    expect(button.textContent).toBe('Read aloud');
  });

  it('speaks the message it belongs to', () => {
    const onSpeak = vi.fn();
    render(<MessageBubble message={answer} onSpeak={onSpeak} />);
    screen.getByRole('button', { name: 'Read aloud' }).click();
    expect(onSpeak).toHaveBeenCalledWith(7);
  });

  it('offers no playback control on the reader’s own messages', () => {
    render(<MessageBubble message={{ ...answer, role: 'user' }} onSpeak={() => {}} />);
    expect(screen.queryByRole('button', { name: /read aloud/i })).not.toBeInTheDocument();
  });
});
