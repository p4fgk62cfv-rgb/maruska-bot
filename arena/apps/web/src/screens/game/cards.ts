import { rankValue, suitOf, SUITS, type CardId, type Suit } from '@arena/game-engine';

/** Suits grouped, trumps last, low to high inside a suit. */
export function sortHand(hand: CardId[], trump: Suit, mode: 'suit' | 'rank'): CardId[] {
  const suitIndex = (c: CardId) => (suitOf(c) === trump ? 10 : SUITS.indexOf(suitOf(c)));
  return [...hand].sort((a, b) =>
    mode === 'suit'
      ? suitIndex(a) - suitIndex(b) || rankValue(a) - rankValue(b)
      : Number(suitOf(a) === trump) - Number(suitOf(b) === trump) || rankValue(a) - rankValue(b) || suitIndex(a) - suitIndex(b),
  );
}

export function sameRank(cards: CardId[]): boolean {
  return new Set(cards.map((c) => c.slice(0, -1))).size <= 1;
}
