import { createDeck, shuffle, type Random } from '../Deck.js';
import type { CardId } from '../Card.js';
import { applyAction, applyTimeout, cloneState, createGame } from '../GameEngine.js';
import type { GameEvent } from '../Actions.js';
import type { GameState, PlayerId } from '../GameState.js';
import type { GameSettings } from '../Rules.js';
import { pendingThrowers, undefendedCount } from '../TurnManager.js';
import type { CardMemory } from './memory.js';
import type { BrainParams } from './params.js';
import { candidates, policyMove, visibleCheats, type BrainMove } from './policy.js';

export interface SearchOptions {
  /** Stop after this many guessed deals… */
  iterations?: number;
  /** …or after this long, whichever comes first. */
  budgetMs?: number;
  random?: () => number;
  /** Candidates looked at (the policy's best ones). */
  width?: number;
}

/** Turns `() => number` into the engine's Random. */
export const toRandom = (random: () => number): Random => ({ int: (n) => Math.floor(random() * n) });

/**
 * The strong bot's move. For each guess of the hidden cards (consistent with everything the bot
 * saw: its hand, the table, the beaten-off pile and the cards others took), every candidate move
 * is played out to the end of the game; the move that most often avoids being the fool wins.
 * Null when the bot has nothing to do now.
 */
export function searchMove(state: GameState, me: PlayerId, memory: CardMemory, params: BrainParams, options: SearchOptions = {}): BrainMove | null {
  const random = options.random ?? Math.random;
  const call = callOut(state, me, params);
  if (call) return call;

  const list = candidates(state, me, params).sort((a, b) => b.score - a.score).slice(0, options.width ?? 8);
  if (list.length === 0) return null;
  if (list.length === 1) return list[0]!.move;

  const iterations = options.iterations ?? 400;
  const deadline = Date.now() + (options.budgetMs ?? 800);
  const wins = new Array<number>(list.length).fill(0);
  const tries = new Array<number>(list.length).fill(0);
  for (let i = 0; i < iterations && (i < 8 || Date.now() < deadline); i++) {
    const world = determinize(state, me, memory, random);
    for (let c = 0; c < list.length; c++) {
      const moved = applyAction(world, me, list[c]!.move, world.updatedAt);
      if (!moved.ok) continue;
      wins[c]! += playout(moved.state, me, params, random);
      tries[c]! += 1;
    }
  }
  const mean = (c: number) => (tries[c]! ? wins[c]! / tries[c]! : -1);
  const best = Math.max(...list.map((_, c) => mean(c)));
  // Moves practically as good as the best one: pick any of them, so the bot is not predictable.
  const n = Math.max(...tries);
  const margin = n >= 40 ? 0.015 : 0;
  const near = list.filter((_, c) => mean(c) >= best - margin);
  return near[Math.floor(random() * near.length)]!.move;
}

/** «С шулерами»: call out a cheat seen on the table — not always, as a person would miss some. */
function callOut(state: GameState, me: PlayerId, params: BrainParams): BrainMove | null {
  for (const seq of visibleCheats(state, me)) {
    // The same decision every time this card is looked at: one roll per card, not per call.
    if (roll(`${state.gameId}:${seq}:${me}`) < params.catchRate) return { type: 'REPORT_CHEAT', seq };
  }
  return null;
}

function roll(key: string): number {
  let h = 2166136261;
  for (let i = 0; i < key.length; i++) h = Math.imul(h ^ key.charCodeAt(i), 16777619) >>> 0;
  return h / 4294967296;
}

/** A full deal that agrees with what `me` knows; the unknown cards are spread at random. */
export function determinize(state: GameState, me: PlayerId, memory: CardMemory, random: () => number): GameState {
  const world = cloneState(state);
  const mine = world.players.find((p) => p.id === me)!;
  const seen = new Set<CardId>([...mine.hand, ...world.discard]);
  for (const pair of world.table) {
    seen.add(pair.attack);
    if (pair.defense) seen.add(pair.defense);
  }
  const trumpInStock = world.deck.length > 0;
  if (trumpInStock) seen.add(world.trump.card);

  const others = world.players.filter((p) => p.id !== me);
  const known = new Map<PlayerId, CardId[]>();
  for (const p of others) {
    const cards = [...new Set(memory[p.id] ?? [])].filter((c) => !seen.has(c)).slice(0, p.hand.length);
    for (const c of cards) seen.add(c);
    known.set(p.id, cards);
  }
  let pool = shuffle(createDeck(world.rules.deckSize as 24 | 36 | 52).filter((c) => !seen.has(c)), toRandom(random));
  const needed = others.reduce((s, p) => s + p.hand.length - known.get(p.id)!.length, 0) + Math.max(0, world.deck.length - 1);
  if (pool.length !== needed) {
    // The memory disagrees with the counts (should not happen): fall back to knowing nothing.
    const base = new Set<CardId>([...mine.hand, ...world.discard, ...world.table.flatMap((p) => (p.defense ? [p.attack, p.defense] : [p.attack]))]);
    if (trumpInStock) base.add(world.trump.card);
    pool = shuffle(createDeck(world.rules.deckSize as 24 | 36 | 52).filter((c) => !base.has(c)), toRandom(random));
    for (const p of others) known.set(p.id, []);
  }
  for (const p of others) {
    const k = known.get(p.id)!;
    p.hand = [...k, ...pool.splice(0, p.hand.length - k.length)];
  }
  world.deck = trumpInStock ? [...pool.splice(0, world.deck.length - 1), world.trump.card] : [];
  return world;
}

/** Everyone plays the policy to the end. 1 — `me` is not the fool, 0 — the fool, ½ — a draw. */
export function playout(state: GameState, me: PlayerId, params: BrainParams, random: () => number, noise = 0.15): number {
  const end = runGame(state, (s, id) => policyMove(s, id, params, random, noise), random, params.catchRate);
  if (end.status !== 'finished' || !end.result) return 0.5;
  if (end.result.kind === 'draw') return 0.5;
  return end.result.loser === me ? 0 : 1;
}

export type Decider = (state: GameState, id: PlayerId) => BrainMove | null;

/**
 * Plays a game on to its end with the given deciders: whoever must move moves (the defender
 * before the throwers), cheats are called out at `catchRate`, and a table where nobody moves is
 * pushed on as the turn timer would.
 */
export function runGame(
  start: GameState,
  decide: Decider,
  random: () => number,
  catchRate = 0,
  maxSteps = 600,
  /** Sees every step's events (to keep the public card memory). */
  onEvents?: (events: GameEvent[]) => void,
): GameState {
  let s = start;
  const called = new Set<number>();
  for (let step = 0; step < maxSteps && s.status === 'playing'; step++) {
    const move = nextMove(s, decide, random, catchRate, called);
    let result = move ? applyAction(s, move.id, move.move, s.updatedAt + 1) : applyTimeout(s, (s.turnDeadline ?? s.updatedAt) + 1);
    // A refused move (should not happen with the policy): let the timer decide.
    if (!result || !result.ok) result = applyTimeout(s, (s.turnDeadline ?? s.updatedAt) + 1);
    if (!result || !result.ok) break;
    s = result.state;
    onEvents?.(result.events);
  }
  return s;
}

function nextMove(s: GameState, decide: Decider, random: () => number, catchRate: number, called: Set<number>): { id: PlayerId; move: BrainMove } | null {
  if (s.rules.fairness === 'cheaters' && s.illegal.length) {
    for (const p of s.players) {
      if (p.status !== 'active') continue;
      for (const seq of visibleCheats(s, p.id)) {
        if (called.has(seq)) continue;
        called.add(seq);
        if (random() < catchRate) return { id: p.id, move: { type: 'REPORT_CHEAT', seq } };
      }
    }
  }
  const order: PlayerId[] = [];
  if (s.phase === 'attack') order.push(s.attacker);
  else {
    if (s.phase === 'defense' && undefendedCount(s) > 0) order.push(s.defender);
    order.push(...pendingThrowers(s));
  }
  for (const id of order) {
    const move = decide(s, id);
    if (move) return { id, move };
  }
  return null;
}

/** A fresh game for training and tests. */
export function newGame(settings: GameSettings, players: PlayerId[], random: () => number): GameState {
  return createGame({ gameId: `sim-${Math.floor(random() * 1e9)}`, settings, playerIds: players, random: toRandom(random), now: 0 }).state;
}
