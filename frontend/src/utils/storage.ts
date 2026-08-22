/** localStorage under the Source key prefix, carrying the old one forward.
 *
 *  The keys were renamed from `news-ai-*` to `source-*` with the rebrand. A
 *  bare rename would have been silent data loss for anyone already using the
 *  app: `client-id` is the `user_id` that owns conversations server-side (see
 *  `client_id_header` in backend/app/api/chat.py), so a fresh id means every
 *  past chat still exists in the database but is invisible to the person who
 *  wrote it. Theme and voice would merely reset, which is milder but still a
 *  preference the reader set on purpose.
 *
 *  So the first read under a new key adopts the old value and writes it back.
 *  The old key is then removed — it has been copied, and leaving it behind
 *  means a second rebrand would find two candidate values with no way to know
 *  which is current.
 *
 *  Every access is guarded: private-mode Safari throws on localStorage, and a
 *  stored preference is never worth a crash.
 */

const PREFIX = 'source-';
const LEGACY_PREFIX = 'news-ai-';

export function readStored(name: string): string | null {
  const key = PREFIX + name;
  try {
    const current = localStorage.getItem(key);
    if (current !== null) return current;

    const legacy = localStorage.getItem(LEGACY_PREFIX + name);
    if (legacy === null) return null;
    localStorage.setItem(key, legacy);
    localStorage.removeItem(LEGACY_PREFIX + name);
    return legacy;
  } catch {
    return null;
  }
}

export function writeStored(name: string, value: string): void {
  try {
    localStorage.setItem(PREFIX + name, value);
  } catch {
    // the choice still applies for this session, it just will not survive
  }
}
