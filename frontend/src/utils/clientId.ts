import { readStored, writeStored } from './storage';

// 'source-client-id', migrated from the old 'news-ai-client-id' on first read —
// a fresh id here would orphan every conversation this browser has written.
const STORAGE_KEY = 'client-id';

function generateClientId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }

  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);

  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;

  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0'));

  return [
    hex.slice(0, 4).join(''),
    hex.slice(4, 6).join(''),
    hex.slice(6, 8).join(''),
    hex.slice(8, 10).join(''),
    hex.slice(10, 16).join(''),
  ].join('-');
}

export function getClientId(): string {
  let id = readStored(STORAGE_KEY);

  if (!id) {
    id = generateClientId();
    writeStored(STORAGE_KEY, id);
  }

  return id;
}