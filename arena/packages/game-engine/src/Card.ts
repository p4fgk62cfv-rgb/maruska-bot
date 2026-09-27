export const SUITS = ['S', 'H', 'D', 'C'] as const;
export type Suit = (typeof SUITS)[number];

export const RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A'] as const;
export type Rank = (typeof RANKS)[number];

/** Compact card id used everywhere on the wire and in state: "6S", "10H", "QD", "AC". */
export type CardId = `${Rank}${Suit}`;

export interface CardParts {
  rank: Rank;
  suit: Suit;
}

const RANK_VALUE: Record<Rank, number> = {
  '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10,
  J: 11, Q: 12, K: 13, A: 14,
};

export function makeCard(rank: Rank, suit: Suit): CardId {
  return `${rank}${suit}`;
}

export function isCardId(value: unknown): value is CardId {
  if (typeof value !== 'string' || value.length < 2 || value.length > 3) return false;
  const suit = value.slice(-1);
  const rank = value.slice(0, -1);
  return (SUITS as readonly string[]).includes(suit) && (RANKS as readonly string[]).includes(rank);
}

export function parseCard(card: CardId): CardParts {
  return { rank: card.slice(0, -1) as Rank, suit: card.slice(-1) as Suit };
}

export function suitOf(card: CardId): Suit {
  return card.slice(-1) as Suit;
}

export function rankOf(card: CardId): Rank {
  return card.slice(0, -1) as Rank;
}

export function rankValue(card: CardId): number {
  return RANK_VALUE[rankOf(card)];
}

export function rankValueOf(rank: Rank): number {
  return RANK_VALUE[rank];
}

/** True when `defense` beats `attack` given the trump suit. */
export function beats(defense: CardId, attack: CardId, trump: Suit): boolean {
  const ds = suitOf(defense);
  const as = suitOf(attack);
  if (ds === as) return rankValue(defense) > rankValue(attack);
  return ds === trump;
}

/** Sort key: non-trumps by rank, then trumps by rank. Used for auto-moves and hand ordering. */
export function cardStrength(card: CardId, trump: Suit): number {
  return rankValue(card) + (suitOf(card) === trump ? 100 : 0);
}

export const SUIT_LABEL_RU: Record<Suit, string> = { S: 'пики', H: 'червы', D: 'бубны', C: 'трефы' };
export const SUIT_SYMBOL: Record<Suit, string> = { S: '♠', H: '♥', D: '♦', C: '♣' };
export const RANK_LABEL_RU: Record<Rank, string> = {
  '2': '2', '3': '3', '4': '4', '5': '5', '6': '6', '7': '7', '8': '8', '9': '9', '10': '10',
  J: 'В', Q: 'Д', K: 'К', A: 'Т',
};
