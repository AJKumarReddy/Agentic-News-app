import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { useVoice } from './useVoice';

/** Availability is passed in now — App probes the backend once and hands this
 *  hook the flag — so these tests need no network stub at all. */
function mount(available = true) {
  return renderHook(() => useVoice(available));
}

describe('useVoice', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('defaults to off so nobody is spoken to unasked', () => {
    const { result } = mount();
    expect(result.current.voice).toBe('off');
  });

  it('persists the choice across mounts', () => {
    const first = mount();
    act(() => first.result.current.setVoice('on'));
    expect(first.result.current.voice).toBe('on');

    const second = mount();
    expect(second.result.current.voice).toBe('on');
  });

  it('reports the availability it was given', () => {
    expect(mount(true).result.current.available).toBe(true);
    expect(mount(false).result.current.available).toBe(false);
  });

  it('offers the suggestion only until the reader answers it', () => {
    const { result } = mount();
    expect(result.current.nudged).toBe(false);

    act(() => result.current.dismissNudge());
    expect(result.current.nudged).toBe(true);

    // and never again, in this or any later session
    expect(mount().result.current.nudged).toBe(true);
  });

  it('treats turning voice on as answering the suggestion', () => {
    const { result } = mount();
    act(() => result.current.setVoice('on'));
    expect(result.current.nudged).toBe(true);
  });

  it('treats an explicit off as answering it too', () => {
    const { result } = mount();
    act(() => result.current.setVoice('off'));
    expect(mount().result.current.nudged).toBe(true);
  });
});
