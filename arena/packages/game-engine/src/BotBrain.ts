import { beats, cardStrength, makeCard, RANKS, rankOf, rankValue, rankValueOf, SUITS, suitOf, type CardId, type Suit } from './Card.js';
import type { PlayerView } from './PlayerView.js';

/**
 * Bot opponent. It decides from the PlayerView with hints only — its own hand, the table, the
 * trump and the card counts — exactly what a person at the table sees. It never looks at other
 * hands or the stock order. The hard bot also remembers the beaten-off cards (the «напомнить
 * отбой» view a person can buy too): at the end of a two-player game that tells it exactly what
 * the opponent holds, so it leads what cannot be beaten.
 */
export type BotLevel = 'easy' | 'normal' | 'hard';

export type BotMove =
  | { type: 'PLAY_CARD'; card: CardId; target?: number }
  | { type: 'PLAY_CARDS'; cards: CardId[] }
  | { type: 'TRANSFER'; card: CardId }
  | { type: 'TAKE_CARDS' }
  | { type: 'PASS' };

const isTrump = (card: CardId, trump: Suit) => suitOf(card) === trump;

/** Cheapest first: non-trumps by rank, then trumps by rank. */
function cheapest(cards: CardId[], trump: Suit): CardId[] {
  return [...cards].sort((a, b) => cardStrength(a, trump) - cardStrength(b, trump));
}

/** A card is «valuable» when it is a trump or a high card — worth keeping while the stock lasts. */
function valuable(card: CardId, trump: Suit): boolean {
  return isTrump(card, trump) || rankValue(card) >= 12; // Q, K, A
}

/**
 * The next move, or null to wait (nothing to do now). `random` makes the easy bot human-ish.
 */
export function chooseBotMove(view: PlayerView, level: BotLevel, random: () => number = Math.random): BotMove | null {
  const me = view.you;
  if (!me || view.status !== 'playing') return null;
  const trump = view.trump.suit;
  const hand = me.hand;
  const early = view.deckCount > 6;
  // The easy bot plays like a beginner (often a random legal move), the normal one
  // slips now and then, the hard one never.
  const sloppy = random() < (level === 'easy' ? 0.4 : level === 'normal' ? 0.2 : 0);
  const rival = level === 'hard' ? knownRivalHand(view) : null;
  // «С шулерами» the hints list rule-breaking cards too; these bots play honestly.
  const tableRanks = new Set(view.table.flatMap((p) => (p.defense ? [rankOf(p.attack), rankOf(p.defense)] : [rankOf(p.attack)])));
  const a = {
    ...view.actions,
    attack: view.phase === 'attack' ? view.actions.attack : view.actions.attack.filter((c) => tableRanks.has(rankOf(c))),
    defend: Object.fromEntries(
      Object.entries(view.actions.defend)
        .map(([card, targets]) => [card, (targets ?? []).filter((i) => view.table[i] && beats(card as CardId, view.table[i]!.attack, view.trump.suit))])
        .filter(([, targets]) => (targets as number[]).length > 0),
    ) as Record<string, number[]>,
  };

  // ── defending ────────────────────────────────────────────
  const undefended = view.table.map((p, i) => ({ p, i })).filter(({ p }) => !p.defense);
  if (me.id === view.defender && view.phase === 'defense' && undefended.length > 0) {
    // Every open card must be beaten; plan them strongest-first so cheap cards are not wasted.
    const plan = planDefense(undefended.map(({ p, i }) => ({ attack: p.attack, index: i })), a.defend, trump);
    // «Переводной»: pass the attack on with a cheap card instead of spending trumps or taking.
    // Every level transfers: the hard one whenever it can with a plain card, the normal one
    // when beating would cost a trump (and often otherwise), the easy one now and then.
    if (a.transfer.length) {
      const card = cheapest(a.transfer, trump)[0]!;
      const costly = !plan || plan.some((m) => isTrump(m.card, trump));
      const chance = level === 'hard' ? 1 : level === 'normal' ? (costly ? 1 : 0.5) : costly ? 0.45 : 0.25;
      if (!isTrump(card, trump) && random() < chance) return { type: 'TRANSFER', card };
    }
    if (!plan) return a.take ? { type: 'TAKE_CARDS' } : null;
    // A beginner gives up on a defence that needs a trump.
    if (level === 'easy' && a.take && plan.some((m) => isTrump(m.card, trump)) && random() < 0.35) return { type: 'TAKE_CARDS' };
    if (level !== 'easy') {
      // Early in the game, burning a big trump on small cards is worse than taking them.
      const trumpsSpent = plan.filter((m) => isTrump(m.card, trump));
      const smallAttack = undefended.every(({ p }) => !isTrump(p.attack, trump) && rankValue(p.attack) <= 10);
      const bigTrump = trumpsSpent.some((m) => rankValue(m.card) >= (level === 'hard' ? 12 : 13));
      if (early && smallAttack && bigTrump && a.take) return { type: 'TAKE_CARDS' };
    }
    const move = sloppy ? plan[Math.floor(random() * plan.length)]! : plan[0]!;
    return { type: 'PLAY_CARD', card: move.card, target: move.index };
  }

  // ── leading a bout ───────────────────────────────────────
  if (view.phase === 'attack' && view.attacker === me.id && a.canAttack) {
    const options = a.attack.length ? a.attack : hand;
    const order = cheapest(options, trump);
    let lead = sloppy ? order[Math.floor(random() * order.length)]! : order[0]!;
    if (rival) {
      // Endgame against one known hand: lead what it cannot beat, with every card of that rank.
      const unbeatable = order.filter((c) => !rival.some((r) => beats(r, c, trump)));
      if (unbeatable.length) {
        const best = unbeatable[0]!;
        const same = unbeatable.filter((c) => rankOf(c) === rankOf(best));
        if (same.length > 1 && same.length <= view.boutLimit) return { type: 'PLAY_CARDS', cards: same };
        return { type: 'PLAY_CARD', card: best };
      }
    }
    if (level === 'hard' && view.deckCount === 0) {
      // Endgame: lead the rank we hold most of — every copy can follow it in.
      const counts = new Map<string, number>();
      for (const c of order) if (!isTrump(c, trump)) counts.set(rankOf(c), (counts.get(rankOf(c)) ?? 0) + 1);
      const best = [...counts.entries()].sort((x, y) => y[1] - x[1])[0];
      if (best && best[1] > 1) lead = order.find((c) => rankOf(c) === best[0])!;
    }
    if (level === 'hard' && !isTrump(lead, trump)) {
      // Lead a pair of the same small rank at once: two cards to beat instead of one.
      const pair = order.filter((c) => rankOf(c) === rankOf(lead) && !isTrump(c, trump));
      if (pair.length > 1 && rankValue(lead) <= 10 && pair.length <= view.boutLimit) return { type: 'PLAY_CARDS', cards: pair };
    }
    return { type: 'PLAY_CARD', card: lead };
  }

  // ── throwing in / passing ────────────────────────────────
  if (a.pass) {
    const taking = view.phase === 'taking';
    const throwable = cheapest(a.attack, trump).filter((c) => {
      if (level === 'easy') return random() < 0.4 && !isTrump(c, trump);
      // While the stock lasts keep trumps and high cards; when the defender takes, unload small ones.
      if (early) return !valuable(c, trump) && (taking || rankValue(c) <= (level === 'hard' ? 10 : 9));
      if (level === 'hard' && view.deckCount === 0) return true; // endgame: every card thrown is one less in hand
      return !isTrump(c, trump) || view.deckCount === 0;
    });
    if (rival && taking === false) {
      // Known hand: throw in what the defender cannot beat first — it has to take everything.
      const killer = throwable.find((c) => !rival.some((r) => beats(r, c, trump)));
      if (a.canAttack && killer) return { type: 'PLAY_CARD', card: killer };
    }
    if (a.canAttack && throwable.length) return { type: 'PLAY_CARD', card: throwable[0]! };
    return { type: 'PASS' };
  }

  if (a.take) return { type: 'TAKE_CARDS' };
  return null;
}

/**
 * One defending card per open attack card, each used once: the strongest attack card picks
 * first, always the cheapest card that beats it. Null when some card cannot be beaten.
 */
function planDefense(open: { attack: CardId; index: number }[], defend: Record<string, number[]>, trump: Suit): { card: CardId; index: number }[] | null {
  const used = new Set<CardId>();
  const plan: { card: CardId; index: number }[] = [];
  const order = [...open].sort((x, y) => cardStrength(y.attack, trump) - cardStrength(x.attack, trump));
  for (const { index } of order) {
    const candidates = cheapest(
      (Object.entries(defend) as [CardId, number[]][]).filter(([card, targets]) => targets.includes(index) && !used.has(card)).map(([card]) => card),
      trump,
    );
    const card = candidates[0];
    if (!card) return null;
    used.add(card);
    plan.push({ card, index });
  }
  // Play the cheapest-cost move first; the rest follow on the next turns.
  return plan.sort((x, y) => cardStrength(x.card, trump) - cardStrength(y.card, trump));
}

/**
 * With the beaten-off cards known and the stock empty, a two-player opponent holds exactly the
 * cards that are nowhere else. Null when that cannot be known.
 */
function knownRivalHand(view: PlayerView): CardId[] | null {
  if (!view.discard || view.deckCount > 0 || view.players.length !== 2 || !view.you) return null;
  const minRank = view.rules.deckSize === 52 ? 2 : view.rules.deckSize === 36 ? 6 : 9;
  const seen = new Set<CardId>([...view.you.hand, ...view.discard]);
  for (const pair of view.table) {
    seen.add(pair.attack);
    if (pair.defense) seen.add(pair.defense);
  }
  const rest: CardId[] = [];
  for (const suit of SUITS) for (const rank of RANKS) if (rankValueOf(rank) >= minRank) {
    const card = makeCard(rank, suit);
    if (!seen.has(card)) rest.push(card);
  }
  const other = view.players.find((p) => p.id !== view.you!.id);
  // Sanity check: the count must match what the opponent holds.
  return other?.cardCount === rest.length ? rest : null;
}
