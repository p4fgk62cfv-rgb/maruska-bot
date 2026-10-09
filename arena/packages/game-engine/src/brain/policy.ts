import { beats, cardStrength, rankOf, rankValue, suitOf, type CardId, type Rank, type Suit } from '../Card.js';
import type { GameState, PlayerId, TablePair } from '../GameState.js';
import { canAttackNow, mayCheat } from '../AttackManager.js';
import { transferOptions } from '../TransferManager.js';
import { attackCapacity, pendingThrowers, ranksOnTable } from '../TurnManager.js';
import { stageOf, type BrainParams, type StageWeights } from './params.js';

/** A move of the strong bot; it can also call out a cheat («С шулерами»). */
export type BrainMove =
  | { type: 'PLAY_CARD'; card: CardId; target?: number }
  | { type: 'PLAY_CARDS'; cards: CardId[] }
  | { type: 'TRANSFER'; card: CardId }
  | { type: 'TAKE_CARDS' }
  | { type: 'PASS' }
  | { type: 'REPORT_CHEAT'; seq: number };

export interface Candidate {
  move: BrainMove;
  /** Policy score: the hand after the move plus the bias for its kind. */
  score: number;
}

const DECK_LOW: Record<number, number> = { 24: 9, 36: 6, 52: 2 };

/**
 * What the bot knows to decide here: its own hand, the table, the trump, card counts and the
 * beaten-off pile. It never reads other hands or the stock order (in a search they are guesses).
 */
export function candidates(state: GameState, me: PlayerId, params: BrainParams): Candidate[] {
  if (state.status !== 'playing') return [];
  const player = state.players.find((p) => p.id === me);
  if (!player || player.status !== 'active') return [];
  const trump = state.trump.suit;
  const w = params[stageOf(state.deck.length)];
  const low = DECK_LOW[state.rules.deckSize] ?? 6;
  const hand = player.hand;
  const value = (cards: readonly CardId[]) => handValue(cards, trump, w, low);
  const without = (cards: readonly CardId[]) => hand.filter((c) => !cards.includes(c));
  const cheat = mayCheat(state, me);
  const out: Candidate[] = [];

  // ── defending ──
  const open = state.table.map((pair, index) => ({ pair, index })).filter(({ pair }) => pair.defense === null);
  if (state.phase === 'defense' && me === state.defender && open.length > 0) {
    const plan = planDefense(open, hand, trump, false);
    if (plan) out.push({ move: { type: 'PLAY_CARD', card: plan[0]!.card, target: plan[0]!.index }, score: value(without(plan.map((m) => m.card))) });
    const tableCards = state.table.flatMap((p) => (p.defense ? [p.attack, p.defense] : [p.attack]));
    out.push({ move: { type: 'TAKE_CARDS' }, score: value([...hand, ...tableCards]) + w.take });
    const seen = new Set<string>();
    for (const card of cheapest(transferOptions(state, me), trump)) {
      // Cards of one rank differ only by suit: one candidate per «is it a trump».
      const kind = suitOf(card) === trump ? 'trump' : 'plain';
      if (seen.has(kind)) continue;
      seen.add(kind);
      out.push({ move: { type: 'TRANSFER', card }, score: value(without([card])) + w.transfer });
    }
    if (cheat && !plan) {
      // No honest defence: cover what can be covered, and slip a cheap card on the rest.
      const crooked = planDefense(open, hand, trump, true);
      const illegal = crooked?.find((m) => !beats(m.card, state.table[m.index]!.attack, trump));
      if (crooked && illegal) {
        const first = crooked.find((m) => beats(m.card, state.table[m.index]!.attack, trump)) ?? illegal;
        out.push({ move: { type: 'PLAY_CARD', card: first.card, target: first.index }, score: value(without(crooked.map((m) => m.card))) + w.cheat });
      }
    }
    return out;
  }

  // ── leading a bout ──
  if (state.phase === 'attack' && me === state.attacker) {
    const limit = Math.max(1, attackCapacity(state));
    for (const [, cards] of byRank(hand, trump)) {
      out.push({ move: { type: 'PLAY_CARD', card: cards[0]! }, score: value(without([cards[0]!])) });
      const plain = cards.filter((c) => suitOf(c) !== trump);
      const group = (plain.length > 1 ? plain : cards).slice(0, limit);
      if (group.length > 1) out.push({ move: { type: 'PLAY_CARDS', cards: group }, score: value(without(group)) + w.lead * (group.length - 1) });
    }
    return out;
  }

  // ── throwing in, or «бито» / «пас» ──
  if ((state.phase === 'defense' || state.phase === 'taking') && pendingThrowers(state).includes(me)) {
    out.push({ move: { type: 'PASS' }, score: value(hand) });
    if (!canAttackNow(state, me)) return out;
    const bias = state.phase === 'taking' ? w.unload : w.throwIn;
    const capacity = attackCapacity(state);
    const ranks = ranksOnTable(state);
    for (const [rank, cards] of byRank(hand, trump)) {
      if (!ranks.has(rank)) continue;
      out.push({ move: { type: 'PLAY_CARD', card: cards[0]! }, score: value(without([cards[0]!])) + bias });
      const group = cards.slice(0, capacity);
      if (group.length > 1) out.push({ move: { type: 'PLAY_CARDS', cards: group }, score: value(without(group)) + bias * group.length });
    }
    if (cheat && capacity > 0) {
      const offRank = cheapest(hand, trump).find((c) => !ranks.has(rankOf(c)) && suitOf(c) !== trump);
      if (offRank) out.push({ move: { type: 'PLAY_CARD', card: offRank }, score: value(without([offRank])) + bias + w.cheat });
    }
    return out;
  }
  return out;
}

/** The policy's own move: the best-scored candidate, with a little noise so it is not a machine. */
export function policyMove(state: GameState, me: PlayerId, params: BrainParams, random: () => number, noise = 0.05): BrainMove | null {
  const list = candidates(state, me, params);
  if (!list.length) return null;
  let best = list[0]!;
  let bestScore = -Infinity;
  for (const c of list) {
    const s = c.score + (noise > 0 ? noise * gumbel(random) : 0);
    if (s > bestScore) {
      bestScore = s;
      best = c;
    }
  }
  return best.move;
}

/**
 * A table card someone else put down against the rules, as anyone at the table can see it:
 * a thrown card of a rank that was not on the table, or a cover that does not beat its card.
 */
export function visibleCheats(state: GameState, me: PlayerId): number[] {
  if (state.rules.fairness !== 'cheaters' || (state.phase !== 'defense' && state.phase !== 'taking')) return [];
  const played: { seq: number; card: CardId; by: PlayerId; cover?: TablePair }[] = [];
  for (const pair of state.table) {
    played.push({ seq: pair.attackSeq, card: pair.attack, by: pair.by });
    if (pair.defense && pair.defenseBy && pair.defenseSeq !== null) played.push({ seq: pair.defenseSeq, card: pair.defense, by: pair.defenseBy, cover: pair });
  }
  played.sort((a, b) => a.seq - b.seq);
  const ranks = new Set<Rank>();
  const found: number[] = [];
  played.forEach((p, i) => {
    const illegal = p.cover ? !beats(p.card, p.cover.attack, state.trump.suit) : i > 0 && !ranks.has(rankOf(p.card));
    ranks.add(rankOf(p.card));
    if (illegal && p.by !== me) found.push(p.seq);
  });
  return found;
}

function handValue(hand: readonly CardId[], trump: Suit, w: StageWeights, low: number): number {
  const span = 14 - low;
  const counts = new Map<string, number>();
  for (const c of hand) counts.set(rankOf(c), (counts.get(rankOf(c)) ?? 0) + 1);
  let v = w.size * hand.length;
  for (const c of hand) {
    const x = (rankValue(c) - low) / span;
    v += suitOf(c) === trump ? w.trump + w.trumpRank * x : w.card * x;
    if ((counts.get(rankOf(c)) ?? 0) > 1) v += w.pair;
  }
  return v;
}

function cheapest(cards: readonly CardId[], trump: Suit): CardId[] {
  return [...cards].sort((a, b) => cardStrength(a, trump) - cardStrength(b, trump));
}

/** Cards of each rank, cheapest first; ranks ordered by their cheapest card. */
function byRank(hand: readonly CardId[], trump: Suit): [Rank, CardId[]][] {
  const groups = new Map<Rank, CardId[]>();
  for (const c of cheapest(hand, trump)) {
    const r = rankOf(c);
    groups.set(r, [...(groups.get(r) ?? []), c]);
  }
  return [...groups];
}

/**
 * One card per open attack card, strongest attack first, always the cheapest card that covers it.
 * With `crooked`, a card that cannot be covered gets the cheapest card left (a cheat). Null when
 * an honest defence is impossible.
 */
function planDefense(open: { pair: TablePair; index: number }[], hand: readonly CardId[], trump: Suit, crooked: boolean): { card: CardId; index: number }[] | null {
  const free = cheapest(hand, trump);
  const plan: { card: CardId; index: number }[] = [];
  const order = [...open].sort((a, b) => cardStrength(b.pair.attack, trump) - cardStrength(a.pair.attack, trump));
  for (const { pair, index } of order) {
    let at = free.findIndex((c) => beats(c, pair.attack, trump));
    if (at < 0) {
      if (!crooked || !free.length) return null;
      at = 0;
    }
    plan.push({ card: free[at]!, index });
    free.splice(at, 1);
  }
  return plan.sort((a, b) => cardStrength(a.card, trump) - cardStrength(b.card, trump));
}

function gumbel(random: () => number): number {
  return -Math.log(-Math.log(Math.min(1 - 1e-12, Math.max(1e-12, random()))));
}

