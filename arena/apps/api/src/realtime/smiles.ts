import { packOfSmile } from '@arena/shared';
import type { Db } from '../db.js';
import { AppError } from '../lib/errors.js';

/** Classic emoji are free; a sticker needs its pack (unless the pack is free in the shop). */
export async function assertSmile(db: Db, userId: string, smile: string): Promise<void> {
  const pack = packOfSmile(smile);
  if (!pack) return;
  const item = await db.item.findUnique({ where: { key: pack }, select: { id: true, price: true } });
  if (!item) throw new AppError('FORBIDDEN');
  if (item.price === 0n) return;
  const owned = await db.userItem.findUnique({ where: { userId_itemId: { userId, itemId: item.id } }, select: { userId: true } });
  if (!owned) throw new AppError('FORBIDDEN');
}
