import {
  applyAction,
  createGame,
  DEFAULT_SETTINGS,
  seededRandom,
  type CardId,
  type GameAction,
  type GameSettings,
  type GameState,
  type PlayerId,
} from '../src/index.js';

export const NOW = 1_700_000_000_000;

export function newGame(settings: Partial<GameSettings> = {}, seed = 1): GameState {
  const merged = { ...DEFAULT_SETTINGS, ...settings };
  const ids = Array.from({ length: merged.players }, (_, i) => `p${i + 1}`);
  return createGame({ gameId: 'g1', settings: merged, playerIds: ids, random: seededRandom(seed), now: NOW }).state;
}

/**
 * Game with hand-picked hands. Trump is fixed via `trump`; the stock holds `deck`
 * followed by the trump card, and p1 attacks p2 in bout 2 (no first-bout limit).
 */
export function arranged(opts: {
  hands: CardId[][];
  deck?: CardId[];
  trump: CardId;
  settings?: Partial<GameSettings>;
  attacker?: PlayerId;
  firstBout?: boolean;
}): GameState {
  const state = newGame({ ...opts.settings, players: opts.hands.length });
  state.players.forEach((p, i) => (p.hand = [...(opts.hands[i] ?? [])]));
  state.deck = opts.deck ? [...opts.deck, opts.trump] : [];
  state.trump = { suit: opts.trump.slice(-1) as GameState['trump']['suit'], card: opts.trump };
  // Past the first «бито» the discard holds something; before it the first-bout cap (5) applies.
  state.discard = opts.firstBout ? [] : ['6S'];
  const attacker = opts.attacker ?? 'p1';
  const seat = state.players.find((p) => p.id === attacker)!.seat;
  state.attacker = attacker;
  state.defender = state.players[(seat + 1) % state.players.length]!.id;
  state.phase = 'attack';
  state.boutNumber = opts.firstBout ? 1 : 2;
  const limit = opts.firstBout ? 5 : 6;
  state.boutLimit = Math.min(limit, state.players.find((p) => p.id === state.defender)!.hand.length);
  state.currentPlayer = attacker;
  state.passed = [];
  return state;
}

export function act(state: GameState, player: PlayerId, action: GameAction): GameState {
  const result = applyAction(state, player, action, NOW);
  if (!result.ok) throw new Error(`${player} ${action.type} rejected: ${result.error}`);
  return result.state;
}

export function reject(state: GameState, player: PlayerId, action: GameAction): string {
  const result = applyAction(state, player, action, NOW);
  if (result.ok) throw new Error(`${player} ${action.type} unexpectedly accepted`);
  return result.error;
}

export function hand(state: GameState, id: PlayerId): CardId[] {
  return state.players.find((p) => p.id === id)!.hand;
}
