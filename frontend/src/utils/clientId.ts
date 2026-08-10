const STORAGE_KEY = 'guardian-client-id';

/**
 * Anonymous per-browser identity. Conversations are scoped to this ID on the
 * backend so one visitor's recent chats are not visible to another.
 * (Not authentication — replace with real user accounts if those arrive.)
 */
export function getClientId(): string {
  let id = localStorage.getItem(STORAGE_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(STORAGE_KEY, id);
  }
  return id;
}
