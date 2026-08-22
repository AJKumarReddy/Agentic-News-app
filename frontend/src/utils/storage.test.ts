import { beforeEach, describe, expect, it, vi } from 'vitest';
import { readStored, writeStored } from './storage';

describe('storage', () => {
  beforeEach(() => localStorage.clear());

  it('writes under the Source prefix', () => {
    writeStored('theme', 'dark');
    expect(localStorage.getItem('source-theme')).toBe('dark');
  });

  it('adopts a value left behind under the old brand prefix', () => {
    // the case that matters: client-id is the user_id owning every
    // conversation, so losing it hides a reader's whole history from them
    localStorage.setItem('news-ai-client-id', 'abc-123');
    expect(readStored('client-id')).toBe('abc-123');
    expect(localStorage.getItem('source-client-id')).toBe('abc-123');
  });

  it('clears the old key once it has been copied', () => {
    localStorage.setItem('news-ai-theme', 'dark');
    readStored('theme');
    expect(localStorage.getItem('news-ai-theme')).toBeNull();
  });

  it('prefers the current key when both exist', () => {
    localStorage.setItem('news-ai-theme', 'light');
    localStorage.setItem('source-theme', 'dark');
    expect(readStored('theme')).toBe('dark');
  });

  it('is null when neither key is set', () => {
    expect(readStored('voice')).toBeNull();
  });

  it('survives a browser that throws on localStorage', () => {
    // private-mode Safari; a stored preference is never worth a crash
    const boom = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('access denied');
    });
    expect(readStored('theme')).toBeNull();
    expect(() => writeStored('theme', 'dark')).not.toThrow();
    boom.mockRestore();
  });
});
