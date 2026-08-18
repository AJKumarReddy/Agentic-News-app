import { describe, expect, it } from 'vitest';
import { appendTranscript } from './transcript';

describe('appendTranscript', () => {
  it('fills an empty box', () => {
    expect(appendTranscript('', 'What did the Fed say?')).toBe('What did the Fed say?');
  });

  it('never discards what was already typed', () => {
    // the one outcome with no undo
    expect(appendTranscript('What did the Fed', 'say about rate cuts?')).toBe(
      'What did the Fed say about rate cuts?',
    );
  });

  it('joins with exactly one space however the box was left', () => {
    expect(appendTranscript('First part   ', 'second part')).toBe('First part second part');
    expect(appendTranscript('First part', '   second part  ')).toBe('First part second part');
  });

  it('leaves the box alone when the recording held no words', () => {
    expect(appendTranscript('Already typed', '   ')).toBe('Already typed');
    expect(appendTranscript('', '')).toBe('');
  });

  it('accumulates across successive dictations', () => {
    const once = appendTranscript('', 'What changed');
    expect(appendTranscript(once, 'in the report?')).toBe('What changed in the report?');
  });
});
