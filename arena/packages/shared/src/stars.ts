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

/** VIP for Telegram Stars: days added to the player's VIP (premium) time. */
export interface VipPlan {
  key: string;
  stars: number;
  days: number;
  label?: string;
}

export const VIP_PLANS: readonly VipPlan[] = [
  { key: 'vip_7', stars: 75, days: 7 },
  { key: 'vip_30', stars: 249, days: 30, label: 'Популярный' },
  { key: 'vip_90', stars: 599, days: 90, label: 'Выгодный' },
];

export const vipPlan = (key: string): VipPlan | undefined => VIP_PLANS.find((p) => p.key === key);

/** What VIP gives, as shown to players (the server applies each of these). */
export const VIP_PERKS: readonly { icon: string; title: string; text: string }[] = [
  { icon: '👑', title: 'Золотая корона', text: 'на аватарке — за столом, в лобби и в профиле её видят все' },
  { icon: '💡', title: 'Подсветка ходов бесплатно', text: 'в каждой партии, без монет' },
  { icon: '📈', title: '×2 рейтинга за победы', text: 'и +50% всем, кто играет за одним столом с вами' },
  { icon: '⬆️', title: 'Ваши столы выше в лобби', text: 'с короной — их замечают первыми' },
];

export type StarOrderStatus = 'PENDING' | 'PAID' | 'REFUNDED';

export interface StarOrderDto {
  id: string;
  pack: string;
  stars: number;
  coins: number;
  /** VIP days (0 for a coin pack). */
  days: number;
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
