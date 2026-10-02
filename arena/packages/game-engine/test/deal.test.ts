import { randomInt } from 'node:crypto';
import { describe, expect, it } from 'vitest';
import { createDeck, createGame, DEFAULT_SETTINGS, isMisdeal, rankOf, shuffle, suitOf, SUITS, type Random } from '../src/index.js';
import { newGame, NOW } from './helpers.js';

/** The same randomness the server uses for live games. */
const crypto: Random = { int: (max) => randomInt(max) };

/** Chi-square statistic of observed counts against a uniform expectation. */
function chiSquare(counts: number[]): number {
  const total = counts.reduce((a, b) => a + b, 0);
  const expected = total / counts.length;
  return counts.reduce((sum, c) => sum + (c - expected) ** 2 / expected, 0);
}

describe('dealing', () => {
  it('«пересдача»: nobody ever starts with five or six cards of one suit', () => {
    expect(isMisdeal(['6S', '7S', '8S', '9S', '10S', 'AH'])).toBe(true);
    expect(isMisdeal(['6S', '7S', '8S', '9S', 'KH', 'AH'])).toBe(false);
    for (let seed = 1; seed <= 3000; seed++) {
      const players = 2 + (seed % 5);
      const deckSize = players > 4 ? 52 : seed % 3 === 0 ? 24 : 36;
      if (deckSize === 24 && players > 4) continue;
      const state = newGame({ players, deckSize }, seed);
      for (const p of state.players) {
        expect(p.hand).toHaveLength(6);
        expect(isMisdeal(p.hand)).toBe(false);
      }
      // Nothing lost or duplicated by the redeal.
      const all = [...state.players.flatMap((p) => p.hand), ...state.deck];
      expect(new Set(all).size).toBe(deckSize);
      expect(state.deck.length ? state.deck[state.deck.length - 1] : state.players.at(-1)!.hand.at(-1)).toBe(state.trump.card);
    }
  });

  it('the shuffle is uniform: every card lands in every position equally often', () => {
    const deck = createDeck(36);
    const rounds = 36_000;
    const positions = Array.from({ length: 36 }, () => 0);
    for (let i = 0; i < rounds; i++) positions[shuffle(deck, crypto).indexOf('AS')]!++;
    // 35 degrees of freedom: 99.9% of fair runs stay under ~66.6.
    expect(chiSquare(positions)).toBeLessThan(66.6);
  });

  it('the trump is random and fair after redeals: suit and rank are uniform, the first move is shared', () => {
    const games = 20_000;
    const suits = new Map<string, number>(SUITS.map((s) => [s, 0]));
    const ranks = new Map<string, number>();
    const firstSeat = [0, 0];
    for (let i = 0; i < games; i++) {
      const { state } = createGame({ gameId: `g${i}`, settings: { ...DEFAULT_SETTINGS, players: 2, deckSize: 36 }, playerIds: ['a', 'b'], random: crypto, now: NOW });
      suits.set(suitOf(state.trump.card), suits.get(suitOf(state.trump.card))! + 1);
      ranks.set(rankOf(state.trump.card), (ranks.get(rankOf(state.trump.card)) ?? 0) + 1);
      firstSeat[state.attacker === 'a' ? 0 : 1]!++;
    }
    // 3 dof → 16.3, 8 dof → 26.1, 1 dof → 10.8 at 99.9%.
    expect(chiSquare([...suits.values()])).toBeLessThan(16.3);
    expect(ranks.size).toBe(9);
    expect(chiSquare([...ranks.values()])).toBeLessThan(26.1);
    expect(chiSquare(firstSeat)).toBeLessThan(10.8);
  });
});
