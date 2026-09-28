import { makeCard, RANKS, rankValueOf, SUITS, type CardId } from './Card.js';

export const DECK_SIZES = [24, 36, 52] as const;
export type DeckSize = (typeof DECK_SIZES)[number];

const LOWEST_RANK: Record<DeckSize, number> = { 24: 9, 36: 6, 52: 2 };

/** Source of randomness. The server passes a crypto-backed implementation; tests pass a seeded one. */
export interface Random {
  /** Uniform integer in [0, maxExclusive). */
  int(maxExclusive: number): number;
}

export function createDeck(size: DeckSize): CardId[] {
  const lowest = LOWEST_RANK[size];
  const cards: CardId[] = [];
  for (const suit of SUITS) {
    for (const rank of RANKS) {
      if (rankValueOf(rank) >= lowest) cards.push(makeCard(rank, suit));
    }
  }
  return cards;
}

/** Fisher–Yates; returns a new array. */
export function shuffle<T>(items: readonly T[], random: Random): T[] {
  const result = [...items];
  for (let i = result.length - 1; i > 0; i--) {
    const j = random.int(i + 1);
    [result[i], result[j]] = [result[j] as T, result[i] as T];
  }
  return result;
}

/** Deterministic PRNG (mulberry32) for tests and replays. Never use for live games. */
export function seededRandom(seed: number): Random {
  let state = seed >>> 0;
  return {
    int(maxExclusive: number) {
      state = (state + 0x6d2b79f5) >>> 0;
      let t = state;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      const value = ((t ^ (t >>> 14)) >>> 0) / 4294967296;
      return Math.floor(value * maxExclusive);
    },
  };
}
