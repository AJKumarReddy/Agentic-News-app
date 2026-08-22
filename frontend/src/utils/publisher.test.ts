import { describe, expect, it } from 'vitest';
import { publisherName } from './publisher';

describe('publisherName', () => {
  it('maps known domains to the newsroom name', () => {
    expect(publisherName('nypost.com')).toBe('NY Post');
    expect(publisherName('cbsnews.com')).toBe('CBS News');
    expect(publisherName('foxnews.com')).toBe('FOX News');
    expect(publisherName('abcnews.go.com')).toBe('ABC News');
    expect(publisherName('bbc.co.uk')).toBe('BBC News');
  });

  it('normalises protocol, www and trailing path', () => {
    expect(publisherName('https://www.nypost.com/')).toBe('NY Post');
    expect(publisherName('WWW.CBSNEWS.COM')).toBe('CBS News');
  });

  it('tidies domains it has no curated name for', () => {
    expect(publisherName('sfgate.com')).toBe('Sfgate');
    expect(publisherName('some-local-paper.co.uk')).toBe('Some Local Paper');
  });

  it('leaves real publisher names untouched', () => {
    expect(publisherName('The Guardian')).toBe('The Guardian');
    expect(publisherName('The New York Times')).toBe('The New York Times');
  });

  it('handles empty input', () => {
    expect(publisherName('')).toBe('');
    expect(publisherName(undefined)).toBe('');
    expect(publisherName(null)).toBe('');
  });
});
