import { useSyncExternalStore } from 'react';
import { safeStorage } from './hooks.js';

export interface Settings {
  sound: boolean;
  vibration: boolean;
  animations: boolean;
  handSort: 'suit' | 'rank';
}

const KEY = 'arena.settings';
const DEFAULTS: Settings = { sound: true, vibration: true, animations: true, handSort: 'suit' };

let current: Settings = { ...DEFAULTS, ...safeStorage.get<Partial<Settings>>(KEY, {}) };
const listeners = new Set<() => void>();

/** Per-device preferences (sound, vibration, animations, hand sorting). */
export const settings = {
  get: (): Settings => current,
  set(patch: Partial<Settings>): void {
    current = { ...current, ...patch };
    safeStorage.set(KEY, current);
    for (const l of listeners) l();
  },
  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};

export function useSettings(): Settings {
  return useSyncExternalStore(settings.subscribe, settings.get, settings.get);
}

export function motionAllowed(): boolean {
  return current.animations && !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
}
