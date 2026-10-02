import { cardStrength, type CardId } from './Card.js';
import { applyAction, legalActions } from './GameEngine.js';
import type { GameState, PlayerId } from './GameState.js';
import type { BotMove } from './BotBrain.js';

/**
 * Exact play for the end of a two-player game. Once the stock is empty, a player who kept
 * track of the beaten-off cards («напомнить отбой») knows the opponent's hand card for card —
 * so searching the real state here uses nothing a careful person could not know.
 *
 * Plain minimax with memo over the engine's own moves; it gives up (null) past a node budget,
 * and the bot then plays by its usual rules.
 */
const WIN = 1;
const LOSS = -1;

class OutOfBudget extends Error {}

export function solveEndgame(state: GameState, me: PlayerId, budget = 20_000): BotMove | null {
  if (state.status !== 'playing' || state.deck.length > 0 || state.players.length !== 2) return null;
  if (state.rules.fairness === 'cheaters') return null;
  const search = new Search(me, budget);
  try {
    const moves = search.movesOf(state, me);
    if (!moves.length) return null;
    let best: { move: BotMove; value: number } | null = null;
    for (const move of moves) {
      const next = search.apply(state, me, move);
      if (!next) continue;
      const value = search.value(next);
      if (!best || value > best.value) best = { move, value };
      if (value === WIN) break;
    }
    // A lost position: leave it to the usual rules (the opponent may still go wrong).
    return best && best.value > LOSS ? best.move : null;
  } catch (error) {
    if (error instanceof OutOfBudget) return null;
    throw error;
  }
}

class Search {
  private nodes = 0;
  private readonly memo = new Map<string, number>();

  constructor(
    private readonly me: PlayerId,
    private readonly budget: number,
  ) {}

  /** Cheapest moves first: a quick win is found before the expensive lines. */
  movesOf(state: GameState, playerId: PlayerId): BotMove[] {
    const a = legalActions(state, playerId);
    const trump = state.trump.suit;
    const cost = (card: CardId) => cardStrength(card, trump);
    const moves: { move: BotMove; order: number }[] = [];
    if (a.canDefend) {
      for (const [card, targets] of Object.entries(a.defend) as [CardId, number[]][]) {
        for (const target of targets) moves.push({ move: { type: 'PLAY_CARD', card, target }, order: cost(card) });
      }
    }
    if (a.canTransfer) for (const card of a.transfer) moves.push({ move: { type: 'TRANSFER', card }, order: cost(card) });
    if (a.canAttack) for (const card of a.attack) moves.push({ move: { type: 'PLAY_CARD', card }, order: cost(card) });
    if (a.pass) moves.push({ move: { type: 'PASS' }, order: 50 });
    if (a.take) moves.push({ move: { type: 'TAKE_CARDS' }, order: 60 });
    return moves.sort((x, y) => x.order - y.order).map((m) => m.move);
  }

  apply(state: GameState, playerId: PlayerId, move: BotMove): GameState | null {
    if (++this.nodes > this.budget) throw new OutOfBudget();
    const result = applyAction(state, playerId, move, state.updatedAt);
    return result.ok ? result.state : null;
  }

  /** Game value for `me`: WIN, LOSS or 0 (draw), with best play from both sides. */
  value(state: GameState): number {
    if (state.status === 'finished') {
      if (!state.loser) return 0;
      return state.loser === this.me ? LOSS : WIN;
    }
    const key = keyOf(state);
    const cached = this.memo.get(key);
    if (cached !== undefined) return cached;

    // Whose move: the one the clock waits for, else whoever can act.
    const order = state.currentPlayer
      ? [state.currentPlayer, ...state.players.map((p) => p.id).filter((id) => id !== state.currentPlayer)]
      : state.players.map((p) => p.id);
    let actor: PlayerId | null = null;
    let moves: BotMove[] = [];
    for (const id of order) {
      moves = this.movesOf(state, id);
      if (moves.length) {
        actor = id;
        break;
      }
    }
    if (!actor) return 0;

    const mine = actor === this.me;
    let best = mine ? -Infinity : Infinity;
    for (const move of moves) {
      const next = this.apply(state, actor, move);
      if (!next) continue;
      const v = this.value(next);
      if (mine ? v > best : v < best) best = v;
      if ((mine && best === WIN) || (!mine && best === LOSS)) break;
    }
    if (!Number.isFinite(best)) best = 0;
    this.memo.set(key, best);
    return best;
  }
}

function keyOf(state: GameState): string {
  const hands = state.players.map((p) => `${p.id}:${[...p.hand].sort().join(',')}`).join('|');
  const table = state.table.map((t) => `${t.attack}>${t.defense ?? ''}`).join(',');
  return `${hands}#${table}#${state.phase}#${state.attacker}#${state.defender}#${state.currentPlayer ?? ''}#${[...state.passed].sort().join(',')}#${state.boutLimit}`;
}
