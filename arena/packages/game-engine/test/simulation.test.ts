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
    if (a.canReport) for (const t of state.table) moves.push({ player: p.id, action: { type: 'REPORT_CHEAT', seq: t.defenseSeq ?? t.attackSeq } });
  }
  return moves.length ? moves[rnd.int(moves.length)]! : null;
}

const TOLERATED = new Set(['NOT_ILLEGAL', 'INVALID_TARGET']);

describe('random full games', () => {
  const variants: Variant[] = ['podkidnoy', 'perevodnoy'];
  const decks = [24, 36, 52] as const;
  for (const variant of variants) {
    for (let players = 2; players <= 6; players++) {
      it(`${variant}, ${players} players: 40 games finish with every card accounted for`, () => {
        for (let seed = 1; seed <= 40; seed++) {
          const rnd = seededRandom(seed * 97 + players);
          const deckSize = players > 4 ? (seed % 2 ? 36 : 52) : decks[seed % 3]!;
          const fairness = seed % 4 === 0 ? 'cheaters' : 'fair';
          let state = newGame(
            { variant, players, deckSize, fairness, throwIn: seed % 2 ? 'all' : 'neighbors', ending: seed % 3 ? 'classic' : 'draw' },
            seed,
          );
          let steps = 0;
          while (state.status === 'playing') {
            steps++;
            expect(steps).toBeLessThan(4000);
            // Timeouts end the game with a forfeit, so only use them rarely.
            const move = rnd.int(200) === 0 ? null : randomMove(state, rnd);
            if (move) {
              const result = applyAction(state, move.player, move.action, NOW + steps);
              if (!result.ok && move.action.type === 'REPORT_CHEAT' && TOLERATED.has(result.error)) continue;
              expect(result.ok, `${move.player} ${JSON.stringify(move.action)} ${result.ok ? '' : result.error}`).toBe(true);
              if (result.ok) state = result.state;
            } else {
              const result = applyTimeout({ ...state, turnDeadline: NOW }, NOW + steps);
              expect(result, 'a stuck game must always have a timeout move').not.toBeNull();
              if (result?.ok) state = result.state;
            }
            const cards = allCards(state);
            expect(cards).toHaveLength(deckSize);
            expect(new Set(cards).size).toBe(deckSize);
            if (state.status === 'playing') {
              const defender = state.players.find((p) => p.id === state.defender)!;
              expect(state.table.filter((t) => !t.defense).length).toBeLessThanOrEqual(defender.hand.length);
              expect(state.table.length).toBeLessThanOrEqual(6);
              if (fairness === 'fair') expect(state.illegal).toEqual([]);
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
