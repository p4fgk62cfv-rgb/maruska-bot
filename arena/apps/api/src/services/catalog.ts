import type { Db } from '../db.js';
import { Ledger } from './ledger.js';
import type { Currency, ItemKind, Rarity } from '../generated/prisma/client.js';

interface AchievementSeed {
  key: string;
  title: string;
  description: string;
  icon: string;
  goal: number;
  reward: number;
}

/** Catalogue is code-owned and upserted on boot, so every environment has the same list. */
export const ACHIEVEMENTS: AchievementSeed[] = [
  { key: 'first_game', title: 'Первая партия', description: 'Сыграйте первую игру', icon: 'cards', goal: 1, reward: 5 },
  { key: 'first_win', title: 'Первая победа', description: 'Выиграйте первую партию', icon: 'trophy', goal: 1, reward: 10 },
  { key: 'wins_10', title: '10 побед', description: 'Выиграйте 10 партий', icon: 'trophy', goal: 10, reward: 20 },
  { key: 'wins_100', title: '100 побед', description: 'Выиграйте 100 партий', icon: 'crown', goal: 100, reward: 100 },
  { key: 'wins_1000', title: 'Легенда стола', description: 'Выиграйте 1000 партий', icon: 'crown', goal: 1000, reward: 500 },
  { key: 'streak_5', title: 'Серия из 5 побед', description: 'Выиграйте 5 партий подряд', icon: 'flame', goal: 5, reward: 30 },
  { key: 'streak_10', title: 'Серия из 10 побед', description: 'Выиграйте 10 партий подряд', icon: 'flame', goal: 10, reward: 80 },
  { key: 'transfer_master', title: 'Мастер перевода', description: 'Переведите атаку 50 раз', icon: 'swap', goal: 50, reward: 40 },
  { key: 'full_table', title: 'Полный стол', description: 'Сыграйте партию вшестером', icon: 'users', goal: 1, reward: 10 },
  { key: 'high_roller', title: 'Крупная ставка', description: 'Сыграйте на ставку 1M', icon: 'gem', goal: 1, reward: 50 },
  { key: 'player_of_day', title: 'Игрок дня', description: 'Больше всех побед за день', icon: 'star', goal: 1, reward: 50 },
  { key: 'social_5', title: 'Компания', description: 'Добавьте 5 друзей', icon: 'heart', goal: 5, reward: 15 },
];

interface ItemSeed {
  key: string;
  kind: ItemKind;
  name: string;
  rarity: Rarity;
  price: number;
  currency: Currency;
  /** Off sale: hidden from the shop; paid copies are refunded once (see retireItems). */
  isActive?: boolean;
}

export const ITEMS: ItemSeed[] = [
  { key: 'back_classic', kind: 'CARD_BACK', name: 'Классическая рубашка', rarity: 'COMMON', price: 0, currency: 'COINS' },
  { key: 'back_violet', kind: 'CARD_BACK', name: 'Неоновый фиолет', rarity: 'RARE', price: 50, currency: 'COINS' },
  { key: 'back_gold', kind: 'CARD_BACK', name: 'Золотой узор', rarity: 'EPIC', price: 150, currency: 'COINS' },
  // Illustrated backs, bought with credits.
  { key: 'back_tartan', kind: 'CARD_BACK', name: 'Шотландка', rarity: 'COMMON', price: 2_500, currency: 'CREDITS' },
  { key: 'back_celtic', kind: 'CARD_BACK', name: 'Кельтский узел', rarity: 'COMMON', price: 2_500, currency: 'CREDITS' },
  { key: 'back_emerald', kind: 'CARD_BACK', name: 'Изумрудный сад', rarity: 'COMMON', price: 2_500, currency: 'CREDITS' },
  { key: 'back_amethyst', kind: 'CARD_BACK', name: 'Аметист', rarity: 'RARE', price: 10_000, currency: 'CREDITS' },
  { key: 'back_frost', kind: 'CARD_BACK', name: 'Морозный узор', rarity: 'RARE', price: 10_000, currency: 'CREDITS' },
  { key: 'back_mandala', kind: 'CARD_BACK', name: 'Золотая мандала', rarity: 'RARE', price: 10_000, currency: 'CREDITS' },
  { key: 'back_crystal', kind: 'CARD_BACK', name: 'Розовый кристалл', rarity: 'RARE', price: 10_000, currency: 'CREDITS' },
  { key: 'back_ruby', kind: 'CARD_BACK', name: 'Рубиновый огонь', rarity: 'EPIC', price: 25_000, currency: 'CREDITS' },
  { key: 'back_moon', kind: 'CARD_BACK', name: 'Лунная ночь', rarity: 'EPIC', price: 25_000, currency: 'CREDITS' },
  { key: 'back_starburst', kind: 'CARD_BACK', name: 'Звёздная вспышка', rarity: 'EPIC', price: 25_000, currency: 'CREDITS' },
  { key: 'back_wolf', kind: 'CARD_BACK', name: 'Волк', rarity: 'LEGENDARY', price: 50_000, currency: 'CREDITS' },
  { key: 'back_spider', kind: 'CARD_BACK', name: 'Паутина', rarity: 'LEGENDARY', price: 50_000, currency: 'CREDITS' },
  // The table is the same «VEGAS» felt for everyone now.
  { key: 'table_felt', kind: 'TABLE', name: 'Зелёное сукно', rarity: 'COMMON', price: 0, currency: 'COINS', isActive: false },
  { key: 'table_midnight', kind: 'TABLE', name: 'Полночь', rarity: 'RARE', price: 80, currency: 'COINS', isActive: false },
  { key: 'frame_silver', kind: 'FRAME', name: 'Серебряная рамка', rarity: 'RARE', price: 60, currency: 'COINS' },
  { key: 'frame_gold', kind: 'FRAME', name: 'Золотая рамка', rarity: 'EPIC', price: 200, currency: 'COINS' },
  { key: 'crown_ruby', kind: 'CROWN', name: 'Рубиновая корона', rarity: 'LEGENDARY', price: 1000, currency: 'COINS' },
  { key: 'emoji_pack_basic', kind: 'EMOJI', name: 'Базовые эмоции', rarity: 'COMMON', price: 0, currency: 'COINS' },
  { key: 'effect_sparks', kind: 'EFFECT', name: 'Искры победы', rarity: 'EPIC', price: 120, currency: 'COINS' },
];

export async function seedCatalog(db: Db): Promise<void> {
  for (const [index, a] of ACHIEVEMENTS.entries()) {
    const data = { ...a, reward: BigInt(a.reward), sortOrder: index };
    await db.achievement.upsert({ where: { key: a.key }, create: data, update: data });
  }
  for (const [index, item] of ITEMS.entries()) {
    const data = { ...item, isActive: item.isActive ?? true, price: BigInt(item.price), sortOrder: index };
    await db.item.upsert({ where: { key: item.key }, create: data, update: data });
  }
  await retireItems(db);
}

/**
 * Items taken off sale go back to their buyers' wallets at the price paid. The ledger key makes it
 * once per player, however many times the server boots; the item then leaves their inventory.
 */
async function retireItems(db: Db): Promise<void> {
  const ledger = new Ledger(db);
  const owned = await db.userItem.findMany({ where: { source: 'shop', item: { isActive: false, price: { gt: 0 } } }, include: { item: true } });
  for (const row of owned) {
    await db.$transaction(async (tx) => {
      await ledger.postIn(tx, {
        userId: row.userId,
        currency: row.item.currency,
        amount: row.item.price,
        type: 'PURCHASE_REFUND',
        source: `item:${row.item.key}`,
        idempotencyKey: `retired:${row.userId}:${row.item.key}`,
      });
      await tx.userItem.delete({ where: { userId_itemId: { userId: row.userId, itemId: row.itemId } } });
    });
  }
}
