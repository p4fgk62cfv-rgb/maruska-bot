import type { Db } from '../db.js';
import { Prisma, type Currency, type TransactionType } from '../generated/prisma/client.js';
import { AppError } from '../lib/errors.js';

export interface LedgerEntry {
  userId: string;
  currency: Currency;
  /** Positive = credit, negative = debit. */
  amount: bigint;
  type: TransactionType;
  source: string;
  /** Unique per business operation; a repeat returns the original entry instead of moving money twice. */
  idempotencyKey: string;
  meta?: Prisma.InputJsonValue;
}

export interface Posted {
  transactionId: string;
  balanceAfter: bigint;
  duplicate: boolean;
}

type Tx = Prisma.TransactionClient;

/**
 * The only code path that changes a balance.
 *
 * - Double spending / races: the balance moves with a single conditional UPDATE
 *   (`balance + amount >= 0`), which row-locks the wallet until commit, plus a CHECK constraint.
 * - Duplicate requests: `idempotency_key` is UNIQUE; a concurrent duplicate fails on insert,
 *   rolls back its balance change and is answered with the first entry.
 * - Client manipulation: amounts come from server rules only; no route accepts an amount.
 */
export class Ledger {
  constructor(private readonly db: Db) {}

  async post(entry: LedgerEntry): Promise<Posted> {
    try {
      return await this.db.$transaction((tx) => this.postIn(tx, entry));
    } catch (error) {
      if (error instanceof Prisma.PrismaClientKnownRequestError && error.code === 'P2002') {
        const existing = await this.db.transaction.findUnique({ where: { idempotencyKey: entry.idempotencyKey } });
        if (existing) return { transactionId: existing.id, balanceAfter: existing.balanceAfter, duplicate: true };
      }
      throw error;
    }
  }

  /** Several entries atomically (e.g. all stakes of one game). Either all post or none. */
  async postMany(entries: LedgerEntry[]): Promise<Posted[]> {
    return this.db.$transaction(async (tx) => {
      const results: Posted[] = [];
      for (const entry of entries) results.push(await this.postIn(tx, entry));
      return results;
    });
  }

  async postIn(tx: Tx, entry: LedgerEntry): Promise<Posted> {
    const existing = await tx.transaction.findUnique({ where: { idempotencyKey: entry.idempotencyKey } });
    if (existing) return { transactionId: existing.id, balanceAfter: existing.balanceAfter, duplicate: true };

    const where: Prisma.WalletWhereInput = { userId: entry.userId, currency: entry.currency };
    if (entry.amount < 0n) where.balance = { gte: -entry.amount };

    const updated = await tx.wallet.updateMany({
      where,
      data: { balance: { increment: entry.amount }, version: { increment: 1 } },
    });
    if (updated.count !== 1) throw new AppError('INSUFFICIENT_FUNDS');

    const wallet = await tx.wallet.findUniqueOrThrow({
      where: { userId_currency: { userId: entry.userId, currency: entry.currency } },
    });

    const row = await tx.transaction.create({
      data: {
        walletId: wallet.id,
        userId: entry.userId,
        currency: entry.currency,
        amount: entry.amount,
        balanceBefore: wallet.balance - entry.amount,
        balanceAfter: wallet.balance,
        type: entry.type,
        source: entry.source,
        idempotencyKey: entry.idempotencyKey,
        meta: entry.meta ?? Prisma.JsonNull,
      },
    });
    return { transactionId: row.id, balanceAfter: wallet.balance, duplicate: false };
  }
}
