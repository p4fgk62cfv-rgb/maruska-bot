import type { CardId } from './Card.js';
import type { GameResult, GameState, PlayerId } from './GameState.js';

/** Actions a player can send. Room-level actions (READY, RECONNECT) live in the server, not the engine. */
export type GameAction =
  | { type: 'PLAY_CARD'; card: CardId; /** table index to beat; required when defending */ target?: number }
  /** Lead or throw in several cards of one rank at once. */
  | { type: 'PLAY_CARDS'; cards: CardId[] }
  | { type: 'TRANSFER'; card: CardId }
  | { type: 'TAKE_CARDS' }
  | { type: 'PASS' }
  /** «Сдаться»: the player gives up and loses. */
  | { type: 'LEAVE_GAME' }
  /** «С шулерами»: point at a table card (by seq) you believe was played illegally. */
  | { type: 'REPORT_CHEAT'; seq: number };

/** Facts produced by the engine. They never contain hidden cards (draw events carry counts only). */
export type GameEvent =
  | { type: 'CARD_PLAYED'; playerId: PlayerId; card: CardId; role: 'attack' | 'defense'; target: number }
  | { type: 'CARD_TRANSFERRED'; playerId: PlayerId; card: CardId; to: PlayerId }
  | { type: 'TAKE_DECLARED'; playerId: PlayerId }
  | { type: 'PASSED'; playerId: PlayerId }
  | { type: 'CARDS_TAKEN'; playerId: PlayerId; cards: CardId[] }
  | { type: 'ROUND_FINISHED'; outcome: 'beaten' | 'taken'; boutNumber: number }
  | { type: 'CARDS_DRAWN'; playerId: PlayerId; count: number }
  | { type: 'PLAYER_OUT'; playerId: PlayerId; place: number }
  | { type: 'PLAYER_LEFT'; playerId: PlayerId; reason: 'surrender' | 'timeout' }
  | { type: 'CHEAT_CAUGHT'; reporter: PlayerId; cheater: PlayerId; returned: { playerId: PlayerId; cards: CardId[] }[] }
  | { type: 'MOVE_UNDONE'; playerId: PlayerId }
  | { type: 'PLAYER_TURN'; playerId: PlayerId | null; phase: string; deadline: number | null }
  | { type: 'GAME_FINISHED'; result: GameResult };

export type EngineErrorCode =
  | 'GAME_FINISHED'
  | 'NOT_A_PLAYER'
  | 'PLAYER_NOT_ACTIVE'
  | 'NOT_YOUR_TURN'
  | 'CARD_NOT_IN_HAND'
  | 'INVALID_CARD'
  | 'RANK_NOT_ON_TABLE'
  | 'BOUT_LIMIT_REACHED'
  | 'THROW_IN_NOT_ALLOWED'
  | 'INVALID_TARGET'
  | 'CARD_DOES_NOT_BEAT'
  | 'TRANSFER_NOT_ALLOWED'
  | 'NOTHING_TO_TAKE'
  | 'CANNOT_PASS'
  | 'NOT_ILLEGAL'
  | 'CANNOT_UNDO'
  | 'BAD_ACTION';

export class EngineError extends Error {
  constructor(public readonly code: EngineErrorCode, message?: string) {
    super(message ?? code);
    this.name = 'EngineError';
  }
}

export type ActionResult =
  | { ok: true; state: GameState; events: GameEvent[] }
  | { ok: false; error: EngineErrorCode };
