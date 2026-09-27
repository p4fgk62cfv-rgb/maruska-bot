import { rankOf, type CardId } from './Card.js';
import { EngineError, type GameEvent } from './Actions.js';
import type { GameState, PlayerId } from './GameState.js';
import { getPlayer, nextActive, ruleBoutLimit, setTurn } from './TurnManager.js';

/**
 * Переводной: before beating anything, the defender may add a card of the same rank
 * and pass the whole attack to the next player, who must be able to answer every card.
 */
export function transferOptions(state: GameState, playerId: PlayerId): CardId[] {
  if (!canTransferNow(state, playerId)) return [];
  const rank = rankOf(state.table[0]!.attack);
  return getPlayer(state, playerId).hand.filter((card) => rankOf(card) === rank);
}

function canTransferNow(state: GameState, playerId: PlayerId): boolean {
  if (state.rules.variant !== 'perevodnoy') return false;
  if (state.phase !== 'defense' || playerId !== state.defender) return false;
  if (state.table.length === 0 || state.table.some((pair) => pair.defense !== null)) return false;
  const rank = rankOf(state.table[0]!.attack);
  if (!state.table.every((pair) => rankOf(pair.attack) === rank)) return false;

  const next = nextActive(state, playerId);
  if (!next) return false;
  const cardsAfter = state.table.length + 1;
  return cardsAfter <= ruleBoutLimit(state) && cardsAfter <= next.hand.length;
}

export function playTransfer(state: GameState, playerId: PlayerId, card: CardId, now: number, events: GameEvent[]): void {
  if (!transferOptions(state, playerId).includes(card)) throw new EngineError('TRANSFER_NOT_ALLOWED');

  const defender = getPlayer(state, playerId);
  const next = nextActive(state, playerId)!;
  defender.hand.splice(defender.hand.indexOf(card), 1);
  state.table.push({ attack: card, defense: null, by: playerId });

  state.attacker = playerId;
  state.defender = next.id;
  state.boutLimit = Math.min(ruleBoutLimit(state), next.hand.length);
  state.passed = [];

  events.push({ type: 'CARD_TRANSFERRED', playerId, card, to: next.id });
  setTurn(state, now, events);
}
