import { describe, expect, it } from 'vitest';
import {
  applyAction,
  applyTimeout,
  legalActions,
  seededRandom,
  toPlayerView,
  type GameAction,
  type GameState,
  type Variant,
} from '../src/index.js';
import { newGame, NOW } from './helpers.js';

function allCards(state: GameState): string[] {
  return [
    ...state.players.flatMap((p) => p.hand),
    ...state.deck,
    ...state.table.flatMap((t) => (t.defense ? [t.attack, t.defense] : [t.attack])),
    ...state.discard,
  ];
}

function randomMove(state: GameState, rnd: ReturnType<typeof seededRandom>): { player: string; action: GameAction } | null {
  const moves: { player: string; action: GameAction }[] = [];
  for (const p of state.players) {
    const a = legalActions(state, p.id);
    for (const card of a.attack) moves.push({ player: p.id, action: { type: 'PLAY_CARD', card } });
    for (const [card, targets] of Object.entries(a.defend)) {
      for (const target of targets ?? []) moves.push({ player: p.id, action: { type: 'PLAY_CARD', card: card as never, target } });
    }
    for (const card of a.transfer) moves.push({ player: p.id, action: { type: 'TRANSFER', card } });
    if (a.take) moves.push({ player: p.id, action: { type: 'TAKE_CARDS' } });
    if (a.pass) moves.push({ player: p.id, action: { type: 'PASS' } });
  }
  return moves.length ? moves[rnd.int(moves.length)]! : null;
}

describe('random full games', () => {
  const variants: Variant[] = ['podkidnoy', 'perevodnoy'];
  for (const variant of variants) {
    for (let players = 2; players <= 6; players++) {
      it(`${variant}, ${players} players: 40 games finish with every card accounted for`, () => {
        for (let seed = 1; seed <= 40; seed++) {
          const rnd = seededRandom(seed * 97 + players);
          let state = newGame({ variant, players, throwIn: seed % 2 ? 'all' : 'neighbors', ending: seed % 3 ? 'classic' : 'draw' }, seed);
          let steps = 0;
          while (state.status === 'playing') {
            steps++;
            expect(steps).toBeLessThan(3000);
            const move = rnd.int(10) === 0 ? null : randomMove(state, rnd);
            if (move) {
              const result = applyAction(state, move.player, move.action, NOW + steps);
              expect(result.ok, `${move.player} ${JSON.stringify(move.action)} ${result.ok ? '' : result.error}`).toBe(true);
              if (result.ok) state = result.state;
            } else {
              state = { ...state, turnDeadline: NOW };
              const result = applyTimeout(state, NOW + steps);
              expect(result, 'a stuck game must always have a timeout move').not.toBeNull();
              if (result?.ok) state = result.state;
            }
            const cards = allCards(state);
            expect(cards).toHaveLength(36);
            expect(new Set(cards).size).toBe(36);
            if (state.status === 'playing') {
              const defender = state.players.find((p) => p.id === state.defender)!;
              expect(state.table.filter((t) => !t.defense).length).toBeLessThanOrEqual(defender.hand.length);
              expect(state.table.length).toBeLessThanOrEqual(6);
              const view = toPlayerView(state, state.players[0]!.id);
              expect(view.you?.hand).toHaveLength(state.players[0]!.hand.length);
            }
          }
          expect(state.result).not.toBeNull();
        }
      });
    }
  }
});
