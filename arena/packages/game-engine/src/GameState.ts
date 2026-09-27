import type { CardId, Suit } from './Card.js';
import type { RuleSet } from './Rules.js';

export type PlayerId = string;

export type PlayerStatus = 'active' | 'out' | 'left';

export interface PlayerState {
  id: PlayerId;
  seat: number;
  hand: CardId[];
  status: PlayerStatus;
  /** 1-based finishing place, set when the player runs out of cards with an empty deck. */
  place: number | null;
}

export interface TablePair {
  attack: CardId;
  defense: CardId | null;
  /** Who put the attacking card down (needed for "last attacker" rules and replays). */
  by: PlayerId;
}

/**
 * attack   — table is empty, the main attacker must lead.
 * defense  — cards are on the table, the defender is beating them, others may throw in.
 * taking   — the defender gave up; others may still throw in before the defender collects.
 * finished — the game is over.
 */
export type Phase = 'attack' | 'defense' | 'taking' | 'finished';

export type GameResult =
  | { kind: 'loser'; loser: PlayerId; reason: 'cards' | 'left' | 'last_attack' }
  | { kind: 'draw' };

export interface GameState {
  gameId: string;
  /** Bumped on every accepted action; clients use it to drop stale updates. */
  version: number;
  status: 'playing' | 'finished';
  phase: Phase;
  rules: RuleSet;
  players: PlayerState[];
  /** Index 0 is the top of the stock. The last card is the face-up trump. */
  deck: CardId[];
  trump: { suit: Suit; card: CardId };
  table: TablePair[];
  discard: CardId[];
  attacker: PlayerId;
  defender: PlayerId;
  /** Player whose move the timer is waiting for. */
  currentPlayer: PlayerId | null;
  /** Max attack cards this bout (min of rule limit and defender's hand at bout start). */
  boutLimit: number;
  boutNumber: number;
  /** Throwers who declared "Пас/Бито" since the last time a new rank appeared on the table. */
  passed: PlayerId[];
  turnDeadline: number | null;
  finishOrder: PlayerId[];
  winner: PlayerId | null;
  loser: PlayerId | null;
  result: GameResult | null;
  createdAt: number;
  updatedAt: number;
}
