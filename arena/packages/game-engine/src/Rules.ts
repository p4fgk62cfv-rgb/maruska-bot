import type { DeckSize } from './Deck.js';

/**
 * The eight lobby "modes" are really four independent pairs of switches:
 *
 *   variant   Подкидной | Переводной
 *   throwIn   Все       | Соседи      (who gets the right to throw in after the attacker says «бито»)
 *   fairness  Честная   | С шулерами
 *   ending    Классика  | Ничья
 *
 * A room picks one value from each pair; the lobby filter matches on any of them.
 */
export type Variant = 'podkidnoy' | 'perevodnoy';
export type ThrowInPolicy = 'all' | 'neighbors';
export type Fairness = 'fair' | 'cheaters';
export type Ending = 'classic' | 'draw';
export type Speed = 'normal' | 'fast';

export interface GameSettings {
  variant: Variant;
  throwIn: ThrowInPolicy;
  fairness: Fairness;
  ending: Ending;
  deckSize: DeckSize;
  players: number;
  speed: Speed;
}

/** Fully resolved rule numbers the engine works with. Derived from settings, never sent by a client. */
export interface RuleSet extends GameSettings {
  handSize: number;
  maxBoutCards: number;
  firstBoutLimit: number;
  turnMs: number;
}

export const MIN_PLAYERS = 2;
export const MAX_PLAYERS = 6;

export const SUPPORTED_DECKS: readonly DeckSize[] = [24, 36, 52];

export const TURN_MS: Record<Speed, number> = { normal: 30_000, fast: 15_000 };

export const DEFAULT_SETTINGS: GameSettings = {
  variant: 'podkidnoy',
  throwIn: 'all',
  fairness: 'fair',
  ending: 'classic',
  deckSize: 36,
  players: 2,
  speed: 'normal',
};

export function resolveRules(settings: GameSettings): RuleSet {
  return {
    ...settings,
    handSize: 6,
    maxBoutCards: 6,
    firstBoutLimit: 5,
    turnMs: TURN_MS[settings.speed],
  };
}

/** Returns a reason string when the settings cannot be played, otherwise null. */
export function validateSettings(settings: GameSettings): string | null {
  if (!Number.isInteger(settings.players) || settings.players < MIN_PLAYERS || settings.players > MAX_PLAYERS) {
    return 'PLAYERS_OUT_OF_RANGE';
  }
  if (!SUPPORTED_DECKS.includes(settings.deckSize)) return 'DECK_NOT_SUPPORTED';
  if (settings.players * 6 > settings.deckSize) return 'DECK_TOO_SMALL';
  return null;
}
