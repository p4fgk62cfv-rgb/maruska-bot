import { EMPTY_FILTER, type RoomFilter } from '@arena/shared';
import { useSyncExternalStore } from 'react';
import { safeStorage } from './hooks.js';

const KEY = 'arena.lobbyFilter.v2';
let current: RoomFilter = { ...EMPTY_FILTER, ...safeStorage.get<Partial<RoomFilter>>(KEY, {}), scope: 'open' };
const listeners = new Set<() => void>();

/** The «Открытые игры» filter: edited on its own screen, read by the lobby, remembered between visits. */
export function useLobbyFilter(): [RoomFilter, (next: RoomFilter) => void] {
  const value = useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => current,
  );
  return [value, setLobbyFilter];
}

export function setLobbyFilter(next: RoomFilter): void {
  current = next;
  safeStorage.set(KEY, next);
  for (const listener of listeners) listener();
}
