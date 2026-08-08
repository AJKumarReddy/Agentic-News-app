import { describe, expect, it } from 'vitest';
import { SSEParser } from './sse';

describe('SSEParser', () => {
  it('parses a complete event', () => {
    const parser = new SSEParser();
    const events = parser.feed('event: token\ndata: {"delta": "Hello"}\n\n');
    expect(events).toEqual([{ type: 'token', delta: 'Hello' }]);
  });

  it('buffers partial events across chunks', () => {
    const parser = new SSEParser();
    expect(parser.feed('event: token\nda')).toEqual([]);
    const events = parser.feed('ta: {"delta": "world"}\n\n');
    expect(events).toEqual([{ type: 'token', delta: 'world' }]);
  });

  it('parses multiple events in one chunk', () => {
    const parser = new SSEParser();
    const events = parser.feed(
      'event: status\ndata: {"stage": "retrieve", "detail": "Retrieving…"}\n\n' +
        'event: done\ndata: {}\n\n',
    );
    expect(events).toHaveLength(2);
    expect(events[0].type).toBe('status');
    expect(events[1].type).toBe('done');
  });

  it('parses sources events with payload', () => {
    const parser = new SSEParser();
    const sources = [
      {
        n: 1,
        article_id: 'tech/2026/a',
        headline: 'Headline',
        url: 'https://www.theguardian.com/x',
        published_at: '2026-08-07',
        section: 'Technology',
        author: 'Jane',
      },
    ];
    const events = parser.feed(`event: sources\ndata: ${JSON.stringify({ sources })}\n\n`);
    expect(events[0]).toEqual({ type: 'sources', sources });
  });

  it('ignores malformed JSON blocks', () => {
    const parser = new SSEParser();
    expect(parser.feed('event: token\ndata: {broken\n\n')).toEqual([]);
  });

  it('parses error events', () => {
    const parser = new SSEParser();
    const events = parser.feed('event: error\ndata: {"detail": "boom"}\n\n');
    expect(events).toEqual([{ type: 'error', detail: 'boom' }]);
  });
});
