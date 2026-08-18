import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/api', () => ({
  getCapabilities: vi.fn(async () => ({ tts: true, stt: true })),
}));

import { getCapabilities } from '../services/api';
import { useCapabilities } from './useCapabilities';

describe('useCapabilities', () => {
  beforeEach(() => {
    vi.mocked(getCapabilities).mockReset();
    vi.mocked(getCapabilities).mockResolvedValue({ tts: true, stt: true });
  });

  it('assumes nothing works until the backend answers', async () => {
    const { result } = renderHook(() => useCapabilities());
    expect(result.current).toEqual({ tts: false, stt: false });
    // let the probe settle inside act, so its resolution does not land after
    // the test and warn
    await act(async () => undefined);
  });

  it('reports what the backend can serve', async () => {
    const { result } = renderHook(() => useCapabilities());
    await waitFor(() => expect(result.current).toEqual({ tts: true, stt: true }));
  });

  it('reads a missing flag as false, not undefined', async () => {
    // a backend deployed before voice input answers with tts alone
    vi.mocked(getCapabilities).mockResolvedValue({ tts: true } as never);
    const { result } = renderHook(() => useCapabilities());
    await waitFor(() => expect(result.current.tts).toBe(true));
    expect(result.current.stt).toBe(false);
  });

  it('treats an unreachable backend as a deployment with the features off', async () => {
    vi.mocked(getCapabilities).mockRejectedValue(new Error('offline'));
    const { result } = renderHook(() => useCapabilities());
    await waitFor(() => expect(result.current).toEqual({ tts: false, stt: false }));
  });

  it('probes once, so two features gating on it cost one request', async () => {
    const { rerender } = renderHook(() => useCapabilities());
    rerender();
    rerender();
    await waitFor(() => expect(getCapabilities).toHaveBeenCalledTimes(1));
  });
});
