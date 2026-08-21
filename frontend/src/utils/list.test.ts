import { describe, expect, it } from 'vitest';
import { joinNames } from './list';

describe('joinNames', () => {
  it('reads as a sentence at three or more', () => {
    // the case that prompted this: join(' and ') gave
    // "The Guardian and The New York Times and TheNewsAPI"
    expect(joinNames(['The Guardian', 'The New York Times', 'TheNewsAPI'])).toBe(
      'The Guardian, The New York Times and TheNewsAPI',
    );
  });

  it('still reads naturally at two', () => {
    expect(joinNames(['The Guardian', 'The New York Times'])).toBe(
      'The Guardian and The New York Times',
    );
  });

  it('leaves a single name alone', () => {
    expect(joinNames(['The Guardian'])).toBe('The Guardian');
  });

  it('is empty when there are no sources, so callers can fall back', () => {
    expect(joinNames([])).toBe('');
  });
});
