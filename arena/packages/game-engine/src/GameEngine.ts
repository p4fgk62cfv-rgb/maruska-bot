import { cardStrength, isCardId, suitOf, type CardId } from './Card.js';
import { createDeck, shuffle, type Random } from './Deck.js';
import { EngineError, type ActionResult, type GameAction, type GameEvent } from './Actions.js';
import type { GameState, PlayerId, PlayerState } from './GameState.js';
import { resolveRules, validateSettings, type GameSettings } from './Rules.js';
import { attackOptions, playAttack, playPass } from './AttackManager.js';
import { declareTake, defenseOptions, playDefense } from './DefenseManager.js';
import { playTransfer, transferOptions } from './TransferManager.js';
import { activePlayers, finishGame, findPlayer, getPlayer, pendingThrowers, setTurn, startBout, undefendedCount } from './TurnManager.js';

export interface CreateGameInput {
  gameId: string;
  settings: GameSettings;
  /** Seat order. Length must equal settings.players. */
  playerIds: PlayerId[];
  random: Random;
  now: number;
}

export function createGame(input: CreateGameInput): { state: GameState; events: GameEvent[] } {
  const problem = validateSettings(input.settings);
  if (problem) throw new Error(problem);
  if (input.playerIds.length !== input.settings.players || new Set(input.playerIds).size !== input.playerIds.length) {
    throw new Error('PLAYER_LIST_INVALID');
  }

  const rules = resolveRules(input.settings);
  const deck = shuffle(createDeck(rules.deckSize), input.random);
  const trumpCard = deck[deck.length - 1] as CardId;

  const players: PlayerState[] = input.playerIds.map((id, seat) => ({ id, seat, hand: [], status: 'active', place: null }));
  const events: GameEvent[] = [];

  // Deal one card at a time, as at a real table.
  for (let round = 0; round < rules.handSize; round++) {
    for (const player of players) player.hand.push(deck.shift() as CardId);
  }
  for (const player of players) events.push({ type: 'CARDS_DRAWN', playerId: player.id, count: player.hand.length });

  const state: GameState = {
    gameId: input.gameId,
    version: 1,
    status: 'playing',
    phase: 'attack',
    rules,
    players,
    deck,
    trump: { suit: suitOf(trumpCard), card: trumpCard },
    table: [],
    discard: [],
    attacker: players[0]!.id,
    defender: players[1]!.id,
    currentPlayer: null,
    boutLimit: 0,
    boutNumber: 0,
    passed: [],
    turnDeadline: null,
    finishOrder: [],
    winner: null,
    loser: null,
    result: null,
    createdAt: input.now,
    updatedAt: input.now,
  };

  startBout(state, firstAttacker(state, input.random));
  setTurn(state, input.now, events);
  return { state, events };
}

/** Lowest trump leads; if nobody has a trump, a random player does. */
function firstAttacker(state: GameState, random: Random): PlayerId {
  let best: { id: PlayerId; strength: number } | null = null;
  for (const player of state.players) {
    for (const card of player.hand) {
      if (suitOf(card) !== state.trump.suit) continue;
      const strength = cardStrength(card, state.trump.suit);
      if (!best || strength < best.strength) best = { id: player.id, strength };
    }
  }
  return best?.id ?? state.players[random.int(state.players.length)]!.id;
}

/**
 * The single entry point for player moves. Pure: the input state is never mutated,
 * a rejected action returns an error code and leaves nothing half-applied.
 */
export function applyAction(state: GameState, playerId: PlayerId, action: GameAction, now: number): ActionResult {
  const next = cloneState(state);
  const events: GameEvent[] = [];
  try {
    dispatch(next, playerId, action, now, events);
  } catch (error) {
    if (error instanceof EngineError) return { ok: false, error: error.code };
    throw error;
  }
  next.version += 1;
  next.updatedAt = now;
  return { ok: true, state: next, events };
}

/** Explicit deep copy: GameState is plain data, and this keeps the engine free of DOM/Node globals. */
export function cloneState(state: GameState): GameState {
  return {
    ...state,
    rules: { ...state.rules },
    players: state.players.map((p) => ({ ...p, hand: [...p.hand] })),
    deck: [...state.deck],
    trump: { ...state.trump },
    table: state.table.map((pair) => ({ ...pair })),
    discard: [...state.discard],
    passed: [...state.passed],
    finishOrder: [...state.finishOrder],
    result: state.result ? { ...state.result } : null,
  };
}

function dispatch(state: GameState, playerId: PlayerId, action: GameAction, now: number, events: GameEvent[]): void {
  if (state.status === 'finished') throw new EngineError('GAME_FINISHED');
  const player = findPlayer(state, playerId);
  if (!player) throw new EngineError('NOT_A_PLAYER');

  if (action.type === 'LEAVE_GAME') {
    leave(state, player, now, events);
    return;
  }
  if (player.status !== 'active') throw new EngineError('PLAYER_NOT_ACTIVE');

  switch (action.type) {
    case 'PLAY_CARD': {
      const card = requireOwnCard(player, action.card);
      if (playerId === state.defender && state.phase === 'defense') {
        playDefense(state, playerId, card, action.target, now, events);
      } else {
        playAttack(state, playerId, card, now, events);
      }
      return;
    }
    case 'TRANSFER':
      playTransfer(state, playerId, requireOwnCard(player, action.card), now, events);
      return;
    case 'TAKE_CARDS':
      declareTake(state, playerId, now, events);
      return;
    case 'PASS':
      playPass(state, playerId, now, events);
      return;
    default:
      throw new EngineError('BAD_ACTION');
  }
}

function requireOwnCard(player: PlayerState, card: unknown): CardId {
  if (!isCardId(card)) throw new EngineError('INVALID_CARD');
  if (!player.hand.includes(card)) throw new EngineError('CARD_NOT_IN_HAND');
  return card;
}

/** Leaving mid-game is a forfeit: the leaver is the fool and the game ends for everyone. */
function leave(state: GameState, player: PlayerState, now: number, events: GameEvent[]): void {
  // A player who already finished keeps their place and may close the game freely.
  if (player.status !== 'active') throw new EngineError('PLAYER_NOT_ACTIVE');
  player.status = 'left';
  events.push({ type: 'PLAYER_LEFT', playerId: player.id });
  finishGame(state, { kind: 'loser', loser: player.id, reason: 'left' }, now, events);
}

/**
 * Server tick: when the turn timer runs out, make the least harmful move for whoever
 * is holding the game up. Returns null when nothing is overdue.
 */
export function applyTimeout(state: GameState, now: number): ActionResult | null {
  if (state.status !== 'playing' || state.turnDeadline === null || now < state.turnDeadline) return null;

  if (state.phase === 'attack') {
    const attacker = getPlayer(state, state.attacker);
    const weakest = [...attacker.hand].sort(
      (a, b) => cardStrength(a, state.trump.suit) - cardStrength(b, state.trump.suit),
    )[0];
    if (!weakest) return null;
    return applyAction(state, attacker.id, { type: 'PLAY_CARD', card: weakest }, now);
  }

  if (state.phase === 'defense' && undefendedCount(state) > 0) {
    return applyAction(state, state.defender, { type: 'TAKE_CARDS' }, now);
  }

  // Throwers are stalling: pass for all of them in one step.
  let current: GameState = state;
  const events: GameEvent[] = [];
  for (const id of pendingThrowers(state)) {
    if (current.status !== 'playing' || current.boutNumber !== state.boutNumber) break;
    const result = applyAction(current, id, { type: 'PASS' }, now);
    if (!result.ok) break;
    current = result.state;
    events.push(...result.events);
  }
  return current === state ? null : { ok: true, state: current, events };
}

export interface AvailableActions {
  attack: CardId[];
  defend: Partial<Record<CardId, number[]>>;
  transfer: CardId[];
  take: boolean;
  pass: boolean;
}

export const NO_ACTIONS: AvailableActions = { attack: [], defend: {}, transfer: [], take: false, pass: false };

/** What the given player may do right now. Drives the client buttons; the server re-validates anyway. */
export function legalActions(state: GameState, playerId: PlayerId): AvailableActions {
  const player = findPlayer(state, playerId);
  if (!player || player.status !== 'active' || state.status !== 'playing') return NO_ACTIONS;

  const isDefender = playerId === state.defender;
  return {
    attack: attackOptions(state, playerId),
    defend: defenseOptions(state, playerId),
    transfer: transferOptions(state, playerId),
    take: isDefender && state.phase === 'defense' && undefendedCount(state) > 0,
    pass: !isDefender && pendingThrowers(state).includes(playerId) && (state.phase === 'defense' || state.phase === 'taking'),
  };
}

export function isGameOver(state: GameState): boolean {
  return state.status === 'finished' || activePlayers(state).length <= 1;
}
