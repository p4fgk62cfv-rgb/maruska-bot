import { safeStorage } from './hooks.js';

const SEEN_KEY = 'arena.chatSeen';

/** The chat was opened: what is there now is read (the «новое» mark on the home tile goes). */
export function markChatSeen(at: string | null): void {
  if (at && at > (safeStorage.get<string | null>(SEEN_KEY, null) ?? '')) safeStorage.set(SEEN_KEY, at);
}

export function chatHasNew(lastAt: string | null): boolean {
  if (!lastAt) return false;
  const seen = safeStorage.get<string | null>(SEEN_KEY, null);
  return !seen || lastAt > seen;
}
