import { DAILY_CREDITS } from '@arena/shared';
import type { Db } from '../db.js';
import { AppError } from '../lib/errors.js';
import type { Ledger } from './ledger.js';

export class WalletService {
  constructor(private readonly db: Db, private readonly ledger: Ledger) {}

  /**
   * 1450 free credits once per 24 hours, only while the balance is below 1450.
   * The wallet row is locked first, so parallel taps cannot both pass the checks;
   * the per-day idempotency key is a second line of defence.
   */
  async claimDailyCredits(userId: string, now = new Date()): Promise<number> {
    return this.db.$transaction(async (tx) => {
      const rows = await tx.$queryRaw<{ balance: bigint }[]>`
        SELECT balance FROM arena.wallets
        WHERE user_id = ${userId}::uuid AND currency = 'CREDITS'::arena."Currency"
        FOR UPDATE`;
      const balance = rows[0]?.balance;
      if (balance === undefined) throw new AppError('UNAUTHORIZED');
      if (balance >= BigInt(DAILY_CREDITS.belowBalance)) throw new AppError('DAILY_CREDITS_BALANCE_TOO_HIGH');

      const last = await tx.transaction.findFirst({
        where: { userId, type: 'DAILY_BONUS' },
        orderBy: { createdAt: 'desc' },
        select: { createdAt: true },
      });
      if (last && now.getTime() - last.createdAt.getTime() < DAILY_CREDITS.cooldownMs) {
        throw new AppError('DAILY_CREDITS_NOT_READY');
      }

      const posted = await this.ledger.postIn(tx, {
        userId,
        currency: 'CREDITS',
        amount: BigInt(DAILY_CREDITS.amount),
        type: 'DAILY_BONUS',
        source: 'daily',
        idempotencyKey: `daily:${userId}:${now.toISOString().slice(0, 10)}`,
      });
      if (posted.duplicate) throw new AppError('DAILY_CREDITS_NOT_READY');
      return Number(posted.balanceAfter);
    });
  }
}
