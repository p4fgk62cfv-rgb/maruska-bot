import { beats, rankOf, type CardId } from './Card.js';
import { EngineError, type GameEvent } from './Actions.js';
import type { GameState, PlayerId } from './GameState.js';
import { getPlayer, ranksOnTable, setTurn, settleBout } from './TurnManager.js';

/** For each card in the defender's hand, the table indices it can beat. */
export function defenseOptions(state: GameState, playerId: PlayerId): Partial<Record<CardId, number[]>> {
  if (state.phase !== 'defense' || playerId !== state.defender) return {};
  const options: Partial<Record<CardId, number[]>> = {};
  for (const card of getPlayer(state, playerId).hand) {
    const targets: number[] = [];
    state.table.forEach((pair, index) => {
      if (pair.defense === null && beats(card, pair.attack, state.trump.suit)) targets.push(index);
    });
    if (targets.length > 0) options[card] = targets;
  }
  return options;
}

export function playDefense(
  state: GameState,
  playerId: PlayerId,
  card: CardId,
  target: number | undefined,
  now: number,
  events: GameEvent[],
): void {
  if (state.phase !== 'defense') throw new EngineError('NOT_YOUR_TURN');
  if (target === undefined || !Number.isInteger(target)) throw new EngineError('INVALID_TARGET');
  const pair = state.table[target];
  if (!pair || pair.defense !== null) throw new EngineError('INVALID_TARGET');
  if (!beats(card, pair.attack, state.trump.suit)) throw new EngineError('CARD_DOES_NOT_BEAT');

  const newRank = !ranksOnTable(state).has(rankOf(card));
  const defender = getPlayer(state, playerId);
  defender.hand.splice(defender.hand.indexOf(card), 1);
  pair.defense = card;
  // A new rank gives throwers new options, so their earlier "pass" no longer holds.
  if (newRank) state.passed = [];

  events.push({ type: 'CARD_PLAYED', playerId, card, role: 'defense', target });
  const bout = state.boutNumber;
  settleBout(state, now, events);
  if (state.status === 'playing' && state.boutNumber === bout) setTurn(state, now, events);
}

export function declareTake(state: GameState, playerId: PlayerId, now: number, events: GameEvent[]): void {
  if (playerId !== state.defender) throw new EngineError('NOT_YOUR_TURN');
  if (state.phase !== 'defense' || !state.table.some((pair) => pair.defense === null)) {
    throw new EngineError('NOTHING_TO_TAKE');
  }
  state.phase = 'taking';
  state.passed = [];
  events.push({ type: 'TAKE_DECLARED', playerId });
  const bout = state.boutNumber;
  settleBout(state, now, events);
  if (state.status === 'playing' && state.boutNumber === bout) setTurn(state, now, events);
}
