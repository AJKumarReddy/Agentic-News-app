import type { ChatStreamEvent, Source } from '../types';

/**
 * Incremental parser for text/event-stream bodies.
 * Feed it decoded chunks; it emits complete events and keeps partials buffered.
 */
export class SSEParser {
  private buffer = '';

  feed(chunk: string): ChatStreamEvent[] {
    this.buffer += chunk;
    const events: ChatStreamEvent[] = [];
    let boundary = this.buffer.indexOf('\n\n');
    while (boundary !== -1) {
      const raw = this.buffer.slice(0, boundary);
      this.buffer = this.buffer.slice(boundary + 2);
      const parsed = this.parseBlock(raw);
      if (parsed) events.push(parsed);
      boundary = this.buffer.indexOf('\n\n');
    }
    return events;
  }

  private parseBlock(block: string): ChatStreamEvent | null {
    let eventName = 'message';
    const dataLines: string[] = [];
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) eventName = line.slice(6).trim();
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
    }
    if (dataLines.length === 0) return null;
    let data: Record<string, unknown> = {};
    try {
      data = JSON.parse(dataLines.join('\n'));
    } catch {
      return null;
    }
    switch (eventName) {
      case 'state':
        return { type: 'state', conversation_id: String(data.conversation_id ?? '') };
      case 'status':
        return { type: 'status', stage: String(data.stage ?? ''), detail: String(data.detail ?? '') };
      case 'token':
        return { type: 'token', delta: String(data.delta ?? '') };
      case 'sources':
        return { type: 'sources', sources: (data.sources as Source[]) ?? [] };
      case 'notice':
        return { type: 'notice', detail: String(data.detail ?? '') };
      case 'done':
        return { type: 'done' };
      case 'error':
        return { type: 'error', detail: String(data.detail ?? 'Unknown error') };
      default:
        return null;
    }
  }
}
