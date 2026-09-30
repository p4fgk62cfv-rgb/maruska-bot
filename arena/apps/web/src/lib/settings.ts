import { useSyncExternalStore } from 'react';
import { safeStorage } from './hooks.js';

export type Theme = 'light' | 'dark' | 'system';

export interface Settings {
  sound: boolean;
  /** Sound volume, 0…1. */
  volume: number;
  vibration: boolean;
  animations: boolean;
  handSort: 'suit' | 'rank';
  /** Highest cards first. */
  sortDesc: boolean;
  /** Double tap on a card plays it at once. */
  doubleTap: boolean;
  /** Action buttons on the right of the dock, helpers on the left (left-handed grip). */
  actionRight: boolean;
  /** Show emoji that other players send. */
  emojis: boolean;
  /** Banknote and confetti after a win. */
  rewardAnimations: boolean;
  theme: Theme;
  /** Home screen visual style. Classic preserves the original design. */
  homeDesign: 'classic' | 'premium';
}

const KEY = 'arena.settings';
const DEFAULTS: Settings = {
  sound: true,
  volume: 0.8,
  vibration: true,
  animations: true,
  handSort: 'suit',
  sortDesc: false,
  doubleTap: true,
  actionRight: false,
  emojis: true,
  rewardAnimations: true,
  theme: 'light',
  homeDesign: 'classic',
};

let current: Settings = { ...DEFAULTS, ...safeStorage.get<Partial<Settings>>(KEY, {}) };
const listeners = new Set<() => void>();

/** Per-device preferences (sound, vibration, animations, hand sorting). */
export const settings = {
  get: (): Settings => current,
  set(patch: Partial<Settings>): void {
    current = { ...current, ...patch };
    safeStorage.set(KEY, current);
    applyTheme();
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

/** «Светлая» is the teal felt, «Тёмная» a night felt; «Системная» follows Telegram or the phone. */
export function applyTheme(): void {
  const tg = (window as { Telegram?: { WebApp?: { colorScheme?: 'light' | 'dark' } } }).Telegram?.WebApp;
  const system = tg?.colorScheme ?? (window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  const theme = current.theme === 'system' ? system : current.theme;
  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.homeDesign = current.homeDesign ?? 'classic';
}

if (typeof window !== 'undefined') applyTheme();
