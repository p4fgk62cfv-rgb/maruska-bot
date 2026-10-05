import { describe, expect, it } from 'vitest';
import {
  applyAction,
  chooseBotMove,
  solveEndgame,
  toPlayerView,
  createDeck,
  DEFAULT_PARAMS,
  determinize,
  mutateParams,
  newGame,
  policyMove,
  rememberEvents,
  runGame,
  sanitizeParams,
  searchMove,
  type CardMemory,
  type Decider,
  type GameSettings,
} from '../src/index.js';

const mulberry = (seed: number) => {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
};
const base: GameSettings = { variant: 'podkidnoy', throwIn: 'all', fairness: 'fair', ending: 'classic', deckSize: 36, players: 2, speed: 'normal' };

describe('the strong bot', () => {
  it.each([
    ['podkidnoy, 2', base],
    ['perevodnoy, 3', { ...base, variant: 'perevodnoy', players: 3 }],
    ['perevodnoy, 4, 52 cards', { ...base, variant: 'perevodnoy', players: 4, deckSize: 52 }],
    ['cheaters, 3', { ...base, variant: 'perevodnoy', players: 3, fairness: 'cheaters' }],
  ] as const)('plays whole games by the rules (%s)', (_, settings) => {
    let refused = 0;
    let finished = 0;
    for (let g = 0; g < 60; g++) {
      const rnd = mulberry(g + 1);
      const ids = Array.from({ length: settings.players }, (_, i) => `p${i}`);
      const decide: Decider = (s, id) => {
        const move = policyMove(s, id, DEFAULT_PARAMS, rnd, 0.1);
        if (move && !applyAction(s, id, move, s.updatedAt + 1).ok) refused++;
        return move;
      };
      const end = runGame(newGame(settings as GameSettings, ids, rnd), decide, rnd, 0.8);
      if (end.status === 'finished') finished++;
    }
    expect(refused).toBe(0);
    expect(finished).toBe(60);
  });

  it('guesses hidden cards only: its own hand, the table and remembered cards stay put, every card is somewhere once', () => {
    const rnd = mulberry(7);
    let s = newGame({ ...base, players: 3 }, ['me', 'b', 'c'], rnd);
    let memory: CardMemory = {};
    // Play a few bouts so somebody takes cards.
    const decide: Decider = (st, id) => policyMove(st, id, DEFAULT_PARAMS, rnd, 0.3);
    s = runGame(s, decide, rnd, 0, 25, (ev) => (memory = rememberEvents(memory, ev)));
    for (let i = 0; i < 20; i++) {
      const world = determinize(s, 'me', memory, rnd);
      expect(world.players.find((p) => p.id === 'me')!.hand).toEqual(s.players.find((p) => p.id === 'me')!.hand);
      expect(world.table).toEqual(s.table);
      expect(world.discard).toEqual(s.discard);
      for (const p of world.players) {
        expect(p.hand.length).toBe(s.players.find((x) => x.id === p.id)!.hand.length);
        for (const c of memory[p.id] ?? []) if (s.players.find((x) => x.id === p.id)!.hand.includes(c)) expect(p.hand).toContain(c);
      }
      expect(world.deck.length).toBe(s.deck.length);
      if (s.deck.length) expect(world.deck.at(-1)).toBe(s.trump.card);
      const all = [...world.players.flatMap((p) => p.hand), ...world.deck, ...world.discard, ...world.table.flatMap((t) => (t.defense ? [t.attack, t.defense] : [t.attack]))];
      expect(new Set(all).size).toBe(all.length);
      expect(all.length).toBe(createDeck(36).length);
    }
  });

  it('remembers what others took from the table and forgets a card once it is played', () => {
    let m: CardMemory = {};
    m = rememberEvents(m, [{ type: 'CARDS_TAKEN', playerId: 'b', cards: ['6S', 'KH'] }]);
    expect(m.b).toEqual(['6S', 'KH']);
    m = rememberEvents(m, [{ type: 'CARD_PLAYED', playerId: 'b', card: '6S', role: 'attack', target: 0 }]);
    expect(m.b).toEqual(['KH']);
  });

  it('search returns a legal move and wins more often than the bare policy', () => {
    let searchWins = 0;
    let games = 0;
    for (let g = 0; g < 16; g++) {
      const rnd = mulberry(100 + Math.floor(g / 2));
      const ids = g % 2 ? ['old', 'new'] : ['new', 'old'];
      const start = newGame(base, ids, rnd);
      const play = mulberry(500 + g);
      let memory: CardMemory = {};
      const decide: Decider = (s, id) => {
        if (id === 'old') return policyMove(s, id, DEFAULT_PARAMS, play, 0.02);
        const move = searchMove(s, id, memory, DEFAULT_PARAMS, { iterations: 30, budgetMs: 5000, random: play });
        if (move) expect(applyAction(s, id, move, s.updatedAt + 1).ok).toBe(true);
        return move;
      };
      const end = runGame(start, decide, play, 0, 600, (ev) => (memory = rememberEvents(memory, ev)));
      if (end.result?.kind === 'loser') {
        games++;
        if (end.result.loser !== 'new') searchWins++;
      }
    }
    expect(searchWins / games).toBeGreaterThanOrEqual(0.5);
  }, 120_000);

  it('training changes weights a little; stored weights are checked', () => {
    const next = mutateParams(DEFAULT_PARAMS, 0.1, mulberry(3));
    expect(next).not.toEqual(DEFAULT_PARAMS);
    expect(Math.abs(next.early.trump - DEFAULT_PARAMS.early.trump)).toBeLessThan(1);
    expect(sanitizeParams({ early: { trump: 'x', size: 1e9 }, catchRate: 7 })).toEqual(DEFAULT_PARAMS);
    expect(sanitizeParams(next)).toEqual(next);
  });

  it('the exact endgame never runs round for ever when cards are taken back and forth («Переводной»)', () => {
    const decide: Decider = (s, id) => {
      if (s.deck.length === 0) {
        const m = solveEndgame(s, id);
        if (m) return m;
      }
      return chooseBotMove(toPlayerView(s, id, { hints: true, discard: true }), 'hard');
    };
    for (let g = 0; g < 80; g++) {
      const rnd = mulberry(900 + g);
      const end = runGame(newGame({ ...base, variant: 'perevodnoy' }, ['a', 'b'], rnd), decide, rnd);
      expect(end.status).toBe('finished');
    }
  }, 120_000);
});
