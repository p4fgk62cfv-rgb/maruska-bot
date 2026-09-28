import { DEFAULT_EQUIPPED, type EquippedDto, type ItemDto } from '@arena/shared';
import type { Db } from '../db.js';
import type { Currency, ItemKind } from '../generated/prisma/client.js';
import { AppError } from '../lib/errors.js';
import { toNumber } from '../lib/money.js';
import type { Ledger } from './ledger.js';

const SLOT: Partial<Record<ItemKind, keyof EquippedDto>> = {
  CARD_BACK: 'cardBack',
  TABLE: 'table',
  FRAME: 'frame',
  CROWN: 'crown',
  EFFECT: 'effect',
};
/** Kinds that may be taken off; a card back and a table are always on. */
const OPTIONAL: ItemKind[] = ['FRAME', 'CROWN', 'EFFECT'];

/** Cosmetics only: nothing here changes rules, odds or rewards. */
export class ItemService {
  constructor(private readonly db: Db, private readonly ledger: Ledger) {}

  async list(userId: string): Promise<ItemDto[]> {
    const [rows, equipped] = await Promise.all([
      this.db.item.findMany({ where: { isActive: true }, orderBy: { sortOrder: 'asc' }, include: { owners: { where: { userId } } } }),
      this.equipped(userId),
    ]);
    const on = new Set(Object.values(equipped).filter(Boolean));
    return rows.map((i) => ({
      key: i.key,
      kind: i.kind,
      name: i.name,
      rarity: i.rarity,
      price: toNumber(i.price),
      currency: i.currency,
      owned: i.price === 0n || i.owners.length > 0,
      equipped: on.has(i.key),
    }));
  }

  async equipped(userId: string): Promise<EquippedDto> {
    const rows = await this.db.userItem.findMany({ where: { userId, equipped: true }, include: { item: true } });
    const result: EquippedDto = { ...DEFAULT_EQUIPPED };
    for (const row of rows) {
      const slot = SLOT[row.item.kind];
      if (slot) (result as unknown as Record<string, string | null>)[slot] = row.item.key;
    }
    return result;
  }

  /** Buys with coins. Buying something you already own is a no-op, never a second charge. */
  async buy(userId: string, key: string): Promise<void> {
    const item = await this.db.item.findUnique({ where: { key } });
    if (!item || !item.isActive) throw new AppError('NOT_FOUND');
    if (item.price === 0n) return;
    try {
      await this.purchase(userId, item.id, key, item.currency, item.price);
    } catch (error) {
      // A parallel tap bought it first: its charge stands, this one rolled back entirely
      // (as a unique conflict, or as «not enough coins» after the first charge).
      const owned = await this.db.userItem.findUnique({ where: { userId_itemId: { userId, itemId: item.id } } });
      if (owned) return;
      throw error;
    }
  }

  private async purchase(userId: string, itemId: string, key: string, currency: Currency, price: bigint): Promise<void> {
    await this.db.$transaction(async (tx) => {
      const owned = await tx.userItem.findUnique({ where: { userId_itemId: { userId, itemId } } });
      if (owned) return;
      await this.ledger.postIn(tx, {
        userId,
        currency,
        amount: -price,
        type: 'PURCHASE',
        source: `item:${key}`,
        idempotencyKey: `item:${userId}:${key}`,
      });
      await tx.userItem.create({ data: { userId, itemId, source: 'shop' } });
    });
  }

  async equip(userId: string, key: string): Promise<EquippedDto> {
    const item = await this.db.item.findUnique({ where: { key } });
    if (!item || !item.isActive || !SLOT[item.kind]) throw new AppError('NOT_FOUND');
    await this.db.$transaction(async (tx) => {
      const owned = await tx.userItem.findUnique({ where: { userId_itemId: { userId, itemId: item.id } } });
      if (!owned && item.price > 0n) throw new AppError('FORBIDDEN');
      await tx.userItem.updateMany({ where: { userId, equipped: true, item: { kind: item.kind } }, data: { equipped: false } });
      await tx.userItem.upsert({
        where: { userId_itemId: { userId, itemId: item.id } },
        create: { userId, itemId: item.id, source: 'free', equipped: true },
        update: { equipped: true },
      });
    });
    return this.equipped(userId);
  }

  async unequip(userId: string, key: string): Promise<EquippedDto> {
    const item = await this.db.item.findUnique({ where: { key } });
    if (!item) throw new AppError('NOT_FOUND');
    if (!OPTIONAL.includes(item.kind)) throw new AppError('VALIDATION_FAILED');
    await this.db.userItem.updateMany({ where: { userId, itemId: item.id }, data: { equipped: false } });
    return this.equipped(userId);
  }
}
