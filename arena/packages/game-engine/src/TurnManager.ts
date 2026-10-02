import { rankOf, type Rank } from './Card.js';
import type { GameEvent } from './Actions.js';
import type { GameState, PlayerId, PlayerState } from './GameState.js';

export function findPlayer(state: GameState, id: PlayerId): PlayerState | undefined {
  return state.players.find((p) => p.id === id);
}

export function getPlayer(state: GameState, id: PlayerId): PlayerState {
  const player = findPlayer(state, id);
  if (!player) throw new Error(`unknown player ${id}`);
  return player;
}

/** Players still in the game (holding cards or able to draw). */
export function activePlayers(state: GameState): PlayerState[] {
  return state.players.filter((p) => p.status === 'active');
}

/** Next active player clockwise after `id`, skipping `exclude`. */
export function nextActive(state: GameState, id: PlayerId, exclude: PlayerId[] = []): PlayerState | undefined {
  const count = state.players.length;
  const from = getPlayer(state, id).seat;
  for (let step = 1; step <= count; step++) {
    const candidate = state.players[(from + step) % count];
    if (candidate && candidate.status === 'active' && !exclude.includes(candidate.id)) return candidate;
  }
  return undefined;
}

/** Previous active player (counter-clockwise) — the defender's other neighbour. */
export function prevActive(state: GameState, id: PlayerId): PlayerState | undefined {
  const count = state.players.length;
  const from = getPlayer(state, id).seat;
  for (let step = 1; step <= count; step++) {
    const candidate = state.players[(from - step + count * 2) % count];
    if (candidate && candidate.status === 'active' && candidate.id !== id) return candidate;
  }
  return undefined;
}

/** Everyone who may throw at the current defender this bout, per the throw-in policy. */
export function throwInPool(state: GameState): PlayerId[] {
  const others = activePlayers(state).filter((p) => p.id !== state.defender);
  if (state.rules.throwIn === 'all') return others.map((p) => p.id);
  const allowed = new Set<PlayerId>([state.attacker]);
  const otherNeighbour = nextActive(state, state.defender);
  if (otherNeighbour) allowed.add(otherNeighbour.id);
  return others.filter((p) => allowed.has(p.id)).map((p) => p.id);
}

/**
 * Who holds the right to throw in right now. The attacker goes first; only after the
 * attacker says «бито» (or runs out of cards) does the right pass to the rest of the pool.
 * A new rank from the defender clears the passes, so the right returns to the attacker.
 */
export function throwers(state: GameState): PlayerId[] {
  const pool = throwInPool(state);
  const attacker = findPlayer(state, state.attacker);
  const attackerHolds =
    pool.includes(state.attacker) && !state.passed.includes(state.attacker) && (attacker?.hand.length ?? 0) > 0;
  return attackerHolds ? [state.attacker] : pool.filter((id) => id !== state.attacker);
}

export function ranksOnTable(state: GameState): Set<Rank> {
  const ranks = new Set<Rank>();
  for (const pair of state.table) {
    ranks.add(rankOf(pair.attack));
    if (pair.defense) ranks.add(rankOf(pair.defense));
  }
  return ranks;
}

export function undefendedCount(state: GameState): number {
  return state.table.filter((pair) => pair.defense === null).length;
}

/** How many more attack cards the table can take right now. */
export function attackCapacity(state: GameState): number {
  const defender = getPlayer(state, state.defender);
  const byLimit = state.boutLimit - state.table.length;
  const byHand = defender.hand.length - undefendedCount(state);
  return Math.max(0, Math.min(byLimit, byHand));
}

/** Throwers who still hold cards and haven't passed — the bout waits for them. */
export function pendingThrowers(state: GameState): PlayerId[] {
  return throwers(state).filter((id) => !state.passed.includes(id) && getPlayer(state, id).hand.length > 0);
}

export function setTurn(state: GameState, now: number, events: GameEvent[]): void {
  let current: PlayerId | null = null;
  if (state.phase === 'attack') current = state.attacker;
  else if (state.phase === 'defense' && undefendedCount(state) > 0) current = state.defender;
  else if (state.phase === 'defense' || state.phase === 'taking') current = pendingThrowers(state)[0] ?? null;

  state.currentPlayer = current;
  state.turnDeadline = state.phase === 'finished' ? null : now + state.rules.turnMs;
  events.push({ type: 'PLAYER_TURN', playerId: current, phase: state.phase, deadline: state.turnDeadline });
}

/**
 * Called after every table change. Ends the bout when nobody can or wants to add cards,
 * then refills hands, retires empty players and checks for the end of the game.
 */
export function settleBout(state: GameState, now: number, events: GameEvent[]): void {
  if (state.phase !== 'defense' && state.phase !== 'taking') return;

  const noMoreAttacks = attackCapacity(state) === 0 || pendingThrowers(state).length === 0;

  if (state.phase === 'defense') {
    if (undefendedCount(state) > 0 || !noMoreAttacks) return;
    endBout(state, 'beaten', now, events);
    return;
  }

  if (!noMoreAttacks) return;
  endBout(state, 'taken', now, events);
}

function endBout(state: GameState, outcome: 'beaten' | 'taken', now: number, events: GameEvent[]): void {
  const defender = getPlayer(state, state.defender);
  const cards = state.table.flatMap((pair) => (pair.defense ? [pair.attack, pair.defense] : [pair.attack]));
  const lastAttacker = state.table[state.table.length - 1]?.by ?? state.attacker;

  if (outcome === 'taken') {
    defender.hand.push(...cards);
    events.push({ type: 'CARDS_TAKEN', playerId: defender.id, cards });
  } else {
    state.discard.push(...cards);
  }
  state.table = [];
  state.passed = [];
  events.push({ type: 'ROUND_FINISHED', outcome, boutNumber: state.boutNumber });

  refillHands(state, events);
  const retired = retireEmptyPlayers(state, events);

  if (finishIfOver(state, retired, lastAttacker, now, events)) return;

  // Beaten: the defender leads next. Taken: the player after the defender leads.
  const leader =
    outcome === 'beaten' && defender.status === 'active'
      ? defender
      : nextActive(state, defender.id);
  if (!leader) throw new Error('no leader for the next bout');
  startBout(state, leader.id);
  setTurn(state, now, events);
}

export function startBout(state: GameState, attacker: PlayerId): void {
  const defender = nextActive(state, attacker);
  if (!defender) throw new Error('no defender for the next bout');
  state.attacker = attacker;
  state.defender = defender.id;
  state.phase = 'attack';
  state.boutNumber += 1;
  state.boutLimit = Math.min(ruleBoutLimit(state), defender.hand.length);
}

/**
 * Rule cap on attack cards for the current bout: 5 until the first «бито» of the game
 * (bouts that ended with «беру» don't count — the discard is still empty), 6 afterwards.
 */
export function ruleBoutLimit(state: GameState): number {
  return state.discard.length === 0 ? state.rules.firstBoutLimit : state.rules.maxBoutCards;
}

/** Main attacker draws first, then the other attackers clockwise, the defender last. */
function refillHands(state: GameState, events: GameEvent[]): void {
  const order: PlayerState[] = [];
  const start = getPlayer(state, state.attacker);
  const count = state.players.length;
  for (let step = 0; step < count; step++) {
    const p = state.players[(start.seat + step) % count];
    if (p && p.status === 'active' && p.id !== state.defender) order.push(p);
  }
  const defender = getPlayer(state, state.defender);
  if (defender.status === 'active') order.push(defender);

  for (const player of order) {
    const need = state.rules.handSize - player.hand.length;
    if (need <= 0 || state.deck.length === 0) continue;
    const drawn = state.deck.splice(0, need);
    player.hand.push(...drawn);
    events.push({ type: 'CARDS_DRAWN', playerId: player.id, count: drawn.length });
  }
}

function retireEmptyPlayers(state: GameState, events: GameEvent[]): PlayerId[] {
  if (state.deck.length > 0) return [];
  const retired: PlayerId[] = [];
  for (const player of state.players) {
    if (player.status === 'active' && player.hand.length === 0) {
      player.status = 'out';
      state.finishOrder.push(player.id);
      player.place = state.finishOrder.length;
      retired.push(player.id);
      events.push({ type: 'PLAYER_OUT', playerId: player.id, place: player.place });
    }
  }
  return retired;
}

function finishIfOver(
  state: GameState,
  retiredNow: PlayerId[],
  lastAttacker: PlayerId,
  now: number,
  events: GameEvent[],
): boolean {
  const remaining = activePlayers(state);
  if (remaining.length > 1) return false;

  const [last] = remaining;
  if (last) {
    finishGame(state, { kind: 'loser', loser: last.id, reason: 'cards' }, now, events);
  } else if (state.rules.ending === 'draw' || !retiredNow.includes(lastAttacker)) {
    // Everyone emptied their hand in the same bout.
    finishGame(state, { kind: 'draw' }, now, events);
  } else {
    // "Классика": the defender beat the very last card, so whoever threw it is the fool.
    finishGame(state, { kind: 'loser', loser: lastAttacker, reason: 'last_attack' }, now, events);
  }
  return true;
}

export function finishGame(
  state: GameState,
  result: NonNullable<GameState['result']>,
  now: number,
  events: GameEvent[],
): void {
  state.status = 'finished';
  state.phase = 'finished';
  state.result = result;
  state.loser = result.kind === 'loser' ? result.loser : null;
  state.winner =
    result.kind === 'draw'
      ? null
      : (state.finishOrder.find((id) => id !== state.loser) ??
        state.players.find((p) => p.id !== state.loser && p.status !== 'left')?.id ??
        null);
  state.currentPlayer = null;
  state.turnDeadline = null;
  state.updatedAt = now;
  events.push({ type: 'GAME_FINISHED', result });
}
