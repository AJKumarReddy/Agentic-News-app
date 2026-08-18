import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/api', () => ({
  getCapabilities: vi.fn(async () => ({ tts: true })),
}));

import { getCapabilities } from '../services/api';
import { useVoice } from './useVoice';

/** Mount and let the capabilities probe settle, so its resolution never
 *  lands outside act() and warns. */
async function mount() {
  const rendered = renderHook(() => useVoice());
  await act(async () => undefined);
  return rendered;
}

describe('useVoice', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(getCapabilities).mockResolvedValue({ tts: true });
  });

  it('defaults to off so nobody is spoken to unasked', async () => {
    const { result } = await mount();
    expect(result.current.voice).toBe('off');
  });

  it('persists the choice across mounts', async () => {
    const first = await mount();
    act(() => first.result.current.setVoice('on'));
    expect(first.result.current.voice).toBe('on');

    const second = await mount();
    expect(second.result.current.voice).toBe('on');
  });

  it('reads availability from the backend', async () => {
    const { result } = await mount();
    await waitFor(() => expect(result.current.available).toBe(true));
  });

  it('hides the feature when the backend cannot serve it', async () => {
    vi.mocked(getCapabilities).mockResolvedValue({ tts: false });
    const { result } = await mount();
    await waitFor(() => expect(result.current.available).toBe(false));
  });

  it('offers the suggestion only until the reader answers it', async () => {
    const { result } = await mount();
    expect(result.current.nudged).toBe(false);

    act(() => result.current.dismissNudge());
    expect(result.current.nudged).toBe(true);

    // and never again, in this or any later session
    const later = await mount();
    expect(later.result.current.nudged).toBe(true);
  });

  it('treats turning voice on as answering the suggestion', async () => {
    const { result } = await mount();
    act(() => result.current.setVoice('on'));
    expect(result.current.nudged).toBe(true);
  });

  it('treats an explicit off as answering it too', async () => {
    const { result } = await mount();
    act(() => result.current.setVoice('off'));
    const later = await mount();
    expect(later.result.current.nudged).toBe(true);
  });
});
