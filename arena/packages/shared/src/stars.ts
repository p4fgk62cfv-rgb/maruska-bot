/**
 * Telegram Stars: packs of coins. Only coins are sold (cosmetics and small in-game extras);
 * credits — the stake currency — are never sold, so the game stays a game (see docs/ARCHITECTURE.md).
 */
export interface StarPack {
  key: string;
  stars: number;
  coins: number;
  /** Extra coins over the base rate, in percent (shown as «+N%»). */
  bonus: number;
  label?: string;
}

/** Base rate: 2 coins per star; bigger packs give more. */
export const STAR_PACKS: readonly StarPack[] = [
  { key: 'coins_50', stars: 25, coins: 50, bonus: 0 },
  { key: 'coins_160', stars: 75, coins: 160, bonus: 7 },
  { key: 'coins_350', stars: 150, coins: 350, bonus: 17, label: 'Популярный' },
  { key: 'coins_900', stars: 350, coins: 900, bonus: 29 },
  { key: 'coins_2000', stars: 750, coins: 2000, bonus: 33, label: 'Выгодный' },
];

export const starPack = (key: string): StarPack | undefined => STAR_PACKS.find((p) => p.key === key);

export type StarOrderStatus = 'PENDING' | 'PAID' | 'REFUNDED';

export interface StarOrderDto {
  id: string;
  pack: string;
  stars: number;
  coins: number;
  status: StarOrderStatus;
  createdAt: string;
  paidAt: string | null;
}

/** The owner's list of purchases. */
export interface OwnerStarOrderDto extends StarOrderDto {
  userId: string;
  name: string;
  refundedAt: string | null;
}

export interface OwnerStarsDto {
  orders: OwnerStarOrderDto[];
  totals: { today: number; month: number; all: number; buyers: number };
}
