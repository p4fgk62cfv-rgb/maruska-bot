import type { CardId } from './Card.js';
import { EngineError, type GameEvent } from './Actions.js';
import type { GameState, PlayerId } from './GameState.js';
import { getPlayer, setTurn } from './TurnManager.js';

/**
 * «С шулерами»: any other player may point at a table card. If it was illegal, that card
 * and every card played after it go back to their owners, and the author is marked as a
 * cheater (no more cheating for the rest of the game). Pointing at a legal card changes nothing.
 */
export function reportCheat(state: GameState, reporter: PlayerId, seq: number, now: number, events: GameEvent[]): void {
  if (state.rules.fairness !== 'cheaters') throw new EngineError('BAD_ACTION');
  if (state.phase !== 'defense' && state.phase !== 'taking') throw new EngineError('INVALID_TARGET');

  const author = authorOf(state, seq);
  if (!author) throw new EngineError('INVALID_TARGET');
  if (author === reporter) throw new EngineError('INVALID_TARGET');
  if (!state.illegal.includes(seq)) throw new EngineError('NOT_ILLEGAL');

  const returned = new Map<PlayerId, CardId[]>();
  const giveBack = (playerId: PlayerId, card: CardId) => {
    getPlayer(state, playerId).hand.push(card);
    returned.set(playerId, [...(returned.get(playerId) ?? []), card]);
  };

  const kept = [];
  for (const pair of state.table) {
    if (pair.attackSeq >= seq) {
      giveBack(pair.by, pair.attack);
      if (pair.defense && pair.defenseBy) giveBack(pair.defenseBy, pair.defense);
      continue;
    }
    if (pair.defense && pair.defenseBy && pair.defenseSeq !== null && pair.defenseSeq >= seq) {
      giveBack(pair.defenseBy, pair.defense);
      pair.defense = null;
      pair.defenseBy = null;
      pair.defenseSeq = null;
    }
    kept.push(pair);
  }
  state.table = kept;
  state.illegal = state.illegal.filter((s) => s < seq);
  if (!state.cheaters.includes(author)) state.cheaters.push(author);
  state.passed = [];
  if (state.table.length === 0) state.phase = 'attack';

  events.push({
    type: 'CHEAT_CAUGHT',
    reporter,
    cheater: author,
    returned: [...returned].map(([playerId, cards]) => ({ playerId, cards })),
  });
  setTurn(state, now, events);
}

function authorOf(state: GameState, seq: number): PlayerId | null {
  for (const pair of state.table) {
    if (pair.attackSeq === seq) return pair.by;
    if (pair.defenseSeq === seq) return pair.defenseBy;
  }
  return null;
}
