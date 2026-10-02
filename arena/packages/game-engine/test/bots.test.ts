import { describe, expect, it } from 'vitest';
import { applyAction, applyTimeout, chooseBotMove, seededRandom, solveEndgame, toPlayerView, type BotLevel, type GameState, type Variant } from '../src/index.js';
import { newGame, NOW } from './helpers.js';

/** Plays a whole game with bots in every seat; returns the fool (or null for a draw). */
function botGame(state: GameState, levels: BotLevel[], seed: number): { state: GameState; timeouts: number } {
  const rnd = seededRandom(seed);
  let steps = 0;
  let timeouts = 0;
  while (state.status === 'playing') {
    steps++;
    if (steps > 3000) throw new Error('game did not finish');
    let moved = false;
    // Whoever has something to do acts; start from a rotating seat like real timing would.
    for (let k = 0; k < state.players.length && !moved; k++) {
      const p = state.players[(steps + k) % state.players.length]!;
      const level = levels[state.players.indexOf(p)]!;
      const exact = level === 'hard' && state.players.length === 2 ? solveEndgame(state, p.id, 5_000) : null;
      const move = exact ?? chooseBotMove(toPlayerView(state, p.id, { hints: true, discard: level === 'hard' }), level, () => rnd.int(1_000_000) / 1_000_000);
      if (!move) continue;
      const result = applyAction(state, p.id, move, NOW + steps);
      if (!result.ok) throw new Error(`${level} bot made an illegal move ${JSON.stringify(move)}: ${result.error}`);
      state = result.state;
      moved = true;
    }
    if (!moved) {
      timeouts++;
      const result = applyTimeout({ ...state, turnDeadline: NOW }, NOW + steps);
      if (!result?.ok) throw new Error('stuck');
      state = result.state;
    }
  }
  return { state, timeouts };
}

describe('bot opponents', () => {
  const variants: Variant[] = ['podkidnoy', 'perevodnoy'];
  for (const variant of variants) {
    it(`${variant}: bots of every level finish games with only legal moves and never stall`, () => {
      for (let seed = 1; seed <= 60; seed++) {
        const players = 2 + (seed % 5);
        const deckSize = players > 4 ? 52 : 36;
        const levels = Array.from({ length: players }, (_, i) => (['easy', 'normal', 'hard'] as const)[(seed + i) % 3]!);
        const { state, timeouts } = botGame(newGame({ variant, players, deckSize }, seed), levels, seed);
        expect(state.status).toBe('finished');
        // A bot always answers in time: nobody loses on the clock.
        expect(timeouts).toBe(0);
        expect(state.result?.kind === 'loser' ? state.result.reason : 'draw').not.toBe('timeout');
      }
    });
  }

  it('a hard bot is the fool less often than an easy one', () => {
    let hardFool = 0;
    let easyFool = 0;
    for (let seed = 1; seed <= 100; seed++) {
      // Alternate seats so the first move does not decide it.
      const hardFirst = seed % 2 === 0;
      const levels: BotLevel[] = hardFirst ? ['hard', 'easy'] : ['easy', 'hard'];
      const { state } = botGame(newGame({ players: 2, deckSize: 36 }, seed), levels, seed);
      const loser = state.result?.kind === 'loser' ? state.result.loser : null;
      if (!loser) continue;
      const hardId = state.players[hardFirst ? 0 : 1]!.id;
      if (loser === hardId) hardFool++;
      else easyFool++;
    }
    expect(hardFool).toBeLessThan(easyFool);
  }, 60_000);

  it('levels are a ladder: normal beats easy, hard beats normal', () => {
    const duel = (x: BotLevel, y: BotLevel, games: number) => {
      let xFool = 0;
      let yFool = 0;
      for (let seed = 1; seed <= games; seed++) {
        const xFirst = seed % 2 === 0;
        const { state } = botGame(newGame({ players: 2, deckSize: 36 }, seed + 5000), xFirst ? [x, y] : [y, x], seed);
        const loser = state.result?.kind === 'loser' ? state.result.loser : null;
        if (!loser) continue;
        if (loser === state.players[xFirst ? 0 : 1]!.id) xFool++;
        else yFool++;
      }
      return yFool / (xFool + yFool);
    };
    expect(duel('normal', 'easy', 150)).toBeGreaterThan(0.7);
    expect(duel('hard', 'normal', 150)).toBeGreaterThan(0.52);
  }, 120_000);

  it('the endgame solver only plays a two-player game with an empty stock, and only legal moves', () => {
    const fresh = newGame({ players: 2, deckSize: 36 }, 3);
    expect(solveEndgame(fresh, fresh.attacker)).toBeNull();
    // Play down to an empty stock, then let the solver move.
    let state = fresh;
    const rnd = seededRandom(3);
    for (let step = 0; state.status === 'playing' && state.deck.length > 0 && step < 2000; step++) {
      const p = state.players[step % 2]!;
      const move = chooseBotMove(toPlayerView(state, p.id, { hints: true }), 'normal', () => rnd.int(1000) / 1000);
      if (!move) continue;
      const r = applyAction(state, p.id, move, NOW + step);
      if (r.ok) state = r.state;
    }
    if (state.status !== 'playing') return;
    for (const p of state.players) {
      const move = solveEndgame(state, p.id);
      if (move) expect(applyAction(state, p.id, move, NOW).ok).toBe(true);
    }
  });

  it('decides from its own view only: nothing to do → waits', () => {
    const state = newGame({ players: 3, deckSize: 36 }, 7);
    const idle = state.players.find((p) => p.id !== state.attacker)!;
    expect(chooseBotMove(toPlayerView(state, idle.id, { hints: true }), 'hard')).toBeNull();
    const lead = chooseBotMove(toPlayerView(state, state.attacker, { hints: true }), 'normal');
    expect(lead?.type).toBe('PLAY_CARD');
  });
});
