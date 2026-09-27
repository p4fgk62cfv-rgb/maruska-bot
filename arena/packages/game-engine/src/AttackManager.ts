import { rankOf, type CardId } from './Card.js';
import { EngineError, type GameEvent } from './Actions.js';
import type { GameState, PlayerId } from './GameState.js';
import { attackCapacity, getPlayer, ranksOnTable, setTurn, settleBout, throwers } from './TurnManager.js';

/** Cards `playerId` may put down as an attack or throw-in right now. */
export function attackOptions(state: GameState, playerId: PlayerId): CardId[] {
  const player = getPlayer(state, playerId);
  if (player.status !== 'active' || playerId === state.defender) return [];

  if (state.phase === 'attack') return playerId === state.attacker ? [...player.hand] : [];
  if (state.phase !== 'defense' && state.phase !== 'taking') return [];
  if (!throwers(state).includes(playerId) || attackCapacity(state) === 0) return [];

  const ranks = ranksOnTable(state);
  return player.hand.filter((card) => ranks.has(rankOf(card)));
}

export function playAttack(state: GameState, playerId: PlayerId, card: CardId, now: number, events: GameEvent[]): void {
  const player = getPlayer(state, playerId);

  if (state.phase === 'attack') {
    if (playerId !== state.attacker) throw new EngineError('NOT_YOUR_TURN');
  } else {
    if (!throwers(state).includes(playerId)) throw new EngineError('THROW_IN_NOT_ALLOWED');
    if (attackCapacity(state) === 0) throw new EngineError('BOUT_LIMIT_REACHED');
    if (!ranksOnTable(state).has(rankOf(card))) throw new EngineError('RANK_NOT_ON_TABLE');
  }

  player.hand.splice(player.hand.indexOf(card), 1);
  state.table.push({ attack: card, defense: null, by: playerId });
  if (state.phase === 'attack') state.phase = 'defense';
  // Throw-ins only repeat ranks already on the table, so earlier passes stay valid.

  events.push({ type: 'CARD_PLAYED', playerId, card, role: 'attack', target: state.table.length - 1 });
  settleBout(state, now, events);
  if (state.status === 'playing' && state.table.length > 0) setTurn(state, now, events);
}

export function playPass(state: GameState, playerId: PlayerId, now: number, events: GameEvent[]): void {
  if (state.phase !== 'defense' && state.phase !== 'taking') throw new EngineError('CANNOT_PASS');
  if (playerId === state.defender || !throwers(state).includes(playerId)) throw new EngineError('CANNOT_PASS');
  if (state.passed.includes(playerId)) throw new EngineError('CANNOT_PASS');

  state.passed.push(playerId);
  events.push({ type: 'PASSED', playerId });
  const tableBefore = state.table.length;
  settleBout(state, now, events);
  if (state.status === 'playing' && state.table.length === tableBefore && tableBefore > 0) setTurn(state, now, events);
}
