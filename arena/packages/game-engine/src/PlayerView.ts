import type { CardId, Suit } from './Card.js';
import type { GameResult, GameState, Phase, PlayerId, PlayerStatus, TablePair } from './GameState.js';
import type { Speed, Variant, ThrowInPolicy, Ending } from './Rules.js';
import { legalActions, NO_ACTIONS, type AvailableActions } from './GameEngine.js';

export interface PublicPlayer {
  id: PlayerId;
  seat: number;
  cardCount: number;
  status: PlayerStatus;
  place: number | null;
}

/**
 * Everything one viewer is allowed to know. Other hands, the stock order and the
 * discard contents never leave the server.
 */
export interface PlayerView {
  gameId: string;
  version: number;
  status: GameState['status'];
  phase: Phase;
  rules: { variant: Variant; throwIn: ThrowInPolicy; ending: Ending; deckSize: number; speed: Speed; turnMs: number };
  players: PublicPlayer[];
  you: { id: PlayerId; hand: CardId[] } | null;
  deckCount: number;
  /** The face-up trump card stays visible while it is still in the stock. */
  trump: { suit: Suit; card: CardId | null };
  table: TablePair[];
  discardCount: number;
  attacker: PlayerId;
  defender: PlayerId;
  currentPlayer: PlayerId | null;
  boutLimit: number;
  boutNumber: number;
  passed: PlayerId[];
  turnDeadline: number | null;
  winner: PlayerId | null;
  loser: PlayerId | null;
  result: GameResult | null;
  actions: AvailableActions;
}

export function toPlayerView(state: GameState, viewer: PlayerId | null): PlayerView {
  const me = viewer ? state.players.find((p) => p.id === viewer) : undefined;
  const { rules } = state;
  return {
    gameId: state.gameId,
    version: state.version,
    status: state.status,
    phase: state.phase,
    rules: {
      variant: rules.variant,
      throwIn: rules.throwIn,
      ending: rules.ending,
      deckSize: rules.deckSize,
      speed: rules.speed,
      turnMs: rules.turnMs,
    },
    players: state.players.map((p) => ({
      id: p.id,
      seat: p.seat,
      cardCount: p.hand.length,
      status: p.status,
      place: p.place,
    })),
    you: me ? { id: me.id, hand: [...me.hand] } : null,
    deckCount: state.deck.length,
    trump: { suit: state.trump.suit, card: state.deck.length > 0 ? state.trump.card : null },
    table: state.table.map((pair) => ({ ...pair })),
    discardCount: state.discard.length,
    attacker: state.attacker,
    defender: state.defender,
    currentPlayer: state.currentPlayer,
    boutLimit: state.boutLimit,
    boutNumber: state.boutNumber,
    passed: [...state.passed],
    turnDeadline: state.turnDeadline,
    winner: state.winner,
    loser: state.loser,
    result: state.result,
    actions: me ? legalActions(state, me.id) : NO_ACTIONS,
  };
}
