import { cardStrength, isCardId, suitOf, type CardId } from './Card.js';
import { createDeck, shuffle, type Random } from './Deck.js';
import { EngineError, type ActionResult, type GameAction, type GameEvent } from './Actions.js';
import type { GameState, PlayerId, PlayerState } from './GameState.js';
import { resolveRules, validateSettings, type GameSettings } from './Rules.js';
import { attackOptions, canAttackNow, playAttackCards, playPass } from './AttackManager.js';
import { reportCheat } from './CheatManager.js';
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
  const players: PlayerState[] = input.playerIds.map((id, seat) => ({ id, seat, hand: [], status: 'active', place: null }));
  const events: GameEvent[] = [];

  // Shuffle and deal one card at a time, as at a real table. Five or more cards of one suit in
  // a hand is a misdeal: the whole deck is reshuffled and dealt again (a fresh shuffle, so every
  // allowed deal stays equally likely and the trump stays random).
  let deck: CardId[] = [];
  let trumpCard: CardId;
  for (let attempt = 0; ; attempt++) {
    deck = shuffle(createDeck(rules.deckSize), input.random);
    // The bottom card is the trump (with a full deal it ends up in the last hand).
    trumpCard = deck[deck.length - 1] as CardId;
    for (const player of players) player.hand = [];
    for (let round = 0; round < rules.handSize; round++) {
      for (const player of players) player.hand.push(deck.shift() as CardId);
    }
    if (!players.some((p) => isMisdeal(p.hand)) || attempt >= MAX_REDEALS) break;
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
    moveSeq: 0,
    illegal: [],
    cheaters: [],
    lastMove: null,
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

/** A misdeal never repeats this often in practice (each deal is fine ~90%+ of the time). */
const MAX_REDEALS = 1000;
/** Cards of one suit in one starting hand that force a redeal. */
export const MISDEAL_SAME_SUIT = 5;

/** «Пересдача»: five (or six) cards of one suit in a starting hand. */
export function isMisdeal(hand: readonly CardId[]): boolean {
  const counts = new Map<string, number>();
  for (const card of hand) {
    const n = (counts.get(suitOf(card)) ?? 0) + 1;
    if (n >= MISDEAL_SAME_SUIT) return true;
    counts.set(suitOf(card), n);
  }
  return false;
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
  const placedCard = action.type === 'PLAY_CARD' || action.type === 'PLAY_CARDS';
  next.lastMove = placedCard && next.status === 'playing' ? { playerId, version: next.version, boutNumber: next.boutNumber } : null;
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
        playAttackCards(state, playerId, [card], now, events);
      }
      return;
    }
    case 'PLAY_CARDS': {
      if (!Array.isArray(action.cards) || action.cards.length > 6) throw new EngineError('BAD_ACTION');
      const cards = action.cards.map((card) => requireOwnCard(player, card));
      playAttackCards(state, playerId, cards, now, events);
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
    case 'REPORT_CHEAT':
      if (!Number.isInteger(action.seq)) throw new EngineError('BAD_ACTION');
      reportCheat(state, playerId, action.seq, now, events);
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

/** «Сдаться» or running out of time: that player loses and the game ends for everyone. */
function forfeit(state: GameState, player: PlayerState, reason: 'surrender' | 'timeout', now: number, events: GameEvent[]): void {
  // A player who already finished keeps their place and may close the game freely.
  if (player.status !== 'active') throw new EngineError('PLAYER_NOT_ACTIVE');
  player.status = 'left';
  events.push({ type: 'PLAYER_LEFT', playerId: player.id, reason });
  finishGame(state, { kind: 'loser', loser: player.id, reason }, now, events);
}

function leave(state: GameState, player: PlayerState, now: number, events: GameEvent[]): void {
  forfeit(state, player, 'surrender', now, events);
}

/**
 * Server tick when the turn timer runs out. A player who must move — the attacker who
 * has to lead, or the defender facing unbeaten cards — loses by timeout. Throwers who
 * merely haven't said «бито»/«пас» are passed automatically. Returns null when nothing is overdue.
 */
export function applyTimeout(state: GameState, now: number): ActionResult | null {
  if (state.status !== 'playing' || state.turnDeadline === null || now < state.turnDeadline) return null;

  const mustMove =
    state.phase === 'attack' ? state.attacker : state.phase === 'defense' && undefendedCount(state) > 0 ? state.defender : null;

  if (mustMove) {
    const next = cloneState(state);
    const events: GameEvent[] = [];
    forfeit(next, getPlayer(next, mustMove), 'timeout', now, events);
    next.version += 1;
    next.lastMove = null;
    return { ok: true, state: next, events };
  }

  let current: GameState = state;
  const events: GameEvent[] = [];
  // Passing hands the right to the next throwers, so keep going until the bout moves on.
  for (let guard = 0; guard < state.players.length * 2; guard++) {
    const pending = pendingThrowers(current);
    if (current.status !== 'playing' || current.boutNumber !== state.boutNumber || pending.length === 0) break;
    for (const id of pending) {
      if (current.boutNumber !== state.boutNumber) break;
      const result = applyAction(current, id, { type: 'PASS' }, now);
      if (!result.ok) break;
      current = result.state;
      events.push(...result.events);
    }
  }
  if (current === state) return null;
  current.lastMove = null;
  return { ok: true, state: current, events };
}

/**
 * «Вернуть карту»: the last card move is taken back, as long as nobody acted after it
 * and it did not end the bout (no cards were drawn). The server keeps `before` — the
 * state right before that move — and charges coins for the undo.
 */
export function undoLastMove(before: GameState, after: GameState, playerId: PlayerId, now: number): ActionResult {
  const move = after.lastMove;
  if (
    after.status !== 'playing' ||
    !move ||
    move.playerId !== playerId ||
    move.version !== after.version ||
    before.version !== after.version - 1 ||
    move.boutNumber !== before.boutNumber
  ) {
    return { ok: false, error: 'CANNOT_UNDO' };
  }
  const restored = cloneState(before);
  restored.version = after.version + 1;
  restored.updatedAt = now;
  restored.lastMove = null;
  const events: GameEvent[] = [{ type: 'MOVE_UNDONE', playerId }];
  setTurn(restored, now, events);
  return { ok: true, state: restored, events };
}

export interface AvailableActions {
  /** Card lists are the «подсветка» hints; see PlayerView options. */
  attack: CardId[];
  defend: Partial<Record<CardId, number[]>>;
  transfer: CardId[];
  /** Whether the player may put an attack card down / defend / transfer at all. Drive the buttons. */
  canAttack: boolean;
  canDefend: boolean;
  canTransfer: boolean;
  take: boolean;
  pass: boolean;
  /** «С шулерами»: pointing at table cards is possible. */
  canReport: boolean;
}

export const NO_ACTIONS: AvailableActions = {
  attack: [],
  defend: {},
  transfer: [],
  canAttack: false,
  canDefend: false,
  canTransfer: false,
  take: false,
  pass: false,
  canReport: false,
};

/** What the given player may do right now. The server re-validates every action anyway. */
export function legalActions(state: GameState, playerId: PlayerId): AvailableActions {
  const player = findPlayer(state, playerId);
  if (!player || player.status !== 'active' || state.status !== 'playing') return NO_ACTIONS;

  const isDefender = playerId === state.defender;
  const defend = defenseOptions(state, playerId);
  const transfer = transferOptions(state, playerId);
  const bout = state.phase === 'defense' || state.phase === 'taking';
  return {
    attack: attackOptions(state, playerId),
    defend,
    transfer,
    canAttack: canAttackNow(state, playerId),
    canDefend: Object.keys(defend).length > 0,
    canTransfer: transfer.length > 0,
    take: isDefender && state.phase === 'defense' && undefendedCount(state) > 0,
    pass: !isDefender && bout && pendingThrowers(state).includes(playerId),
    canReport: state.rules.fairness === 'cheaters' && bout && state.table.length > 0,
  };
}

export function isGameOver(state: GameState): boolean {
  return state.status === 'finished' || activePlayers(state).length <= 1;
}
