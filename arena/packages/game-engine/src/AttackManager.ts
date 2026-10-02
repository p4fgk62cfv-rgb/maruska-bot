import { rankOf, type CardId } from './Card.js';
import { EngineError, type GameEvent } from './Actions.js';
import type { GameState, PlayerId } from './GameState.js';
import { attackCapacity, getPlayer, ranksOnTable, setTurn, settleBout, throwers } from './TurnManager.js';

/** «С шулерами»: a player not yet caught may put down cards that break the rules. */
export function mayCheat(state: GameState, playerId: PlayerId): boolean {
  return state.rules.fairness === 'cheaters' && !state.cheaters.includes(playerId);
}

/** Cards `playerId` may put down as an attack or throw-in right now. */
export function attackOptions(state: GameState, playerId: PlayerId): CardId[] {
  const player = getPlayer(state, playerId);
  if (!canAttackNow(state, playerId)) return [];
  if (state.phase === 'attack' || mayCheat(state, playerId)) return [...player.hand];
  const ranks = ranksOnTable(state);
  return player.hand.filter((card) => ranks.has(rankOf(card)));
}

/** Whether the player holds the right to put an attack card down at all (ignores which card). */
export function canAttackNow(state: GameState, playerId: PlayerId): boolean {
  const player = getPlayer(state, playerId);
  if (player.status !== 'active' || playerId === state.defender || player.hand.length === 0) return false;
  if (state.phase === 'attack') return playerId === state.attacker;
  if (state.phase !== 'defense' && state.phase !== 'taking') return false;
  return throwers(state).includes(playerId) && attackCapacity(state) > 0;
}

export function playAttack(state: GameState, playerId: PlayerId, card: CardId, events: GameEvent[]): void {
  const player = getPlayer(state, playerId);
  let illegal = false;

  if (state.phase === 'attack') {
    if (playerId !== state.attacker) throw new EngineError('NOT_YOUR_TURN');
  } else {
    if (!throwers(state).includes(playerId)) throw new EngineError('THROW_IN_NOT_ALLOWED');
    if (attackCapacity(state) === 0) throw new EngineError('BOUT_LIMIT_REACHED');
    if (!ranksOnTable(state).has(rankOf(card))) {
      if (!mayCheat(state, playerId)) throw new EngineError('RANK_NOT_ON_TABLE');
      illegal = true;
    }
  }

  player.hand.splice(player.hand.indexOf(card), 1);
  const seq = ++state.moveSeq;
  state.table.push({ attack: card, by: playerId, attackSeq: seq, defense: null, defenseBy: null, defenseSeq: null });
  if (illegal) state.illegal.push(seq);
  if (state.phase === 'attack') state.phase = 'defense';
  // Legal throw-ins only repeat ranks already on the table, so earlier passes stay valid.

  events.push({ type: 'CARD_PLAYED', playerId, card, role: 'attack', target: state.table.length - 1 });
}

/** One move of one or more same-rank cards. Settles the bout once, after all cards are down. */
export function playAttackCards(state: GameState, playerId: PlayerId, cards: CardId[], now: number, events: GameEvent[]): void {
  if (cards.length === 0 || new Set(cards).size !== cards.length) throw new EngineError('BAD_ACTION');
  if (new Set(cards.map(rankOf)).size !== 1) throw new EngineError('RANK_NOT_ON_TABLE');
  // Validate the entire batch before changing the cloned state. In particular, the first
  // bout is capped at five attack cards even when the opening move contains several cards.
  if (cards.length > attackCapacity(state)) throw new EngineError('BOUT_LIMIT_REACHED');
  for (const card of cards) playAttack(state, playerId, card, events);
  settleBout(state, now, events);
  if (state.status === 'playing' && state.table.length > 0) setTurn(state, now, events);
}

export function playPass(state: GameState, playerId: PlayerId, now: number, events: GameEvent[]): void {
  if (state.phase !== 'defense' && state.phase !== 'taking') throw new EngineError('CANNOT_PASS');
  if (playerId === state.defender || !throwers(state).includes(playerId)) throw new EngineError('CANNOT_PASS');
  if (state.passed.includes(playerId)) throw new EngineError('CANNOT_PASS');

  state.passed.push(playerId);
  events.push({ type: 'PASSED', playerId });
  const bout = state.boutNumber;
  settleBout(state, now, events);
  if (state.status === 'playing' && state.boutNumber === bout) setTurn(state, now, events);
}
