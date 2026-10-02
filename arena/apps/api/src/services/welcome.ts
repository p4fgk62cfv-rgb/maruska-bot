import type { WelcomeGiftDto } from '@arena/shared';
import type { Db } from '../db.js';
import type { Ledger } from './ledger.js';

const KEY = 'welcome_gift';

/** The welcome gift for newcomers, and the owner's one-off «раздать всем, у кого мало». */
export class WelcomeService {
  private cached: { at: number; value: WelcomeGiftDto } | null = null;

  constructor(
    private readonly db: Db,
    private readonly ledger: Ledger,
    /** What newcomers get until the owner changes it in «Управление» (SIGNUP_BONUS_* variables). */
    private readonly defaults: WelcomeGiftDto,
  ) {}

  async get(): Promise<WelcomeGiftDto> {
    if (this.cached && Date.now() - this.cached.at < 30_000) return this.cached.value;
    const row = await this.db.setting.findUnique({ where: { key: KEY } });
    const value = { ...this.defaults, ...((row?.value as Partial<WelcomeGiftDto> | null) ?? {}) };
    this.cached = { at: Date.now(), value };
    return value;
  }

  async set(value: WelcomeGiftDto): Promise<WelcomeGiftDto> {
    await this.db.setting.upsert({ where: { key: KEY }, create: { key: KEY, value: { ...value } }, update: { value: { ...value } } });
    this.cached = { at: Date.now(), value };
    return value;
  }

  /** Called once, right after an account is created. Idempotent per user and currency. */
  async give(userId: string): Promise<void> {
    const gift = await this.get();
    if (!gift.enabled) return;
    if (gift.credits > 0) {
      await this.ledger.post({ userId, currency: 'CREDITS', amount: BigInt(gift.credits), type: 'SIGNUP_BONUS', source: 'signup', idempotencyKey: `signup:${userId}` });
    }
    if (gift.coins > 0) {
      await this.ledger.post({ userId, currency: 'COINS', amount: BigInt(gift.coins), type: 'SIGNUP_BONUS', source: 'signup', idempotencyKey: `signup-coins:${userId}` });
    }
  }

  /**
   * Gives credits and coins to every player who has fewer than `below` credits. `batch` makes a
   * repeated call (double tap, retry) a no-op for players already paid in this batch.
   */
  async grantToPoor(opts: { below: number; credits: number; coins: number; batch: string; by: string }): Promise<{ players: number }> {
    const poor = await this.db.wallet.findMany({
      where: { currency: 'CREDITS', balance: { lt: BigInt(opts.below) }, user: { profile: { isNot: null }, isBot: false, bannedAt: null } },
      select: { userId: true },
    });
    for (const { userId } of poor) {
      const meta = { reason: 'Подарок от администрации', by: opts.by, batch: opts.batch };
      if (opts.credits > 0) {
        await this.ledger.post({ userId, currency: 'CREDITS', amount: BigInt(opts.credits), type: 'ADMIN', source: `grant:${opts.batch}`, idempotencyKey: `grant:${opts.batch}:${userId}:c`, meta });
      }
      if (opts.coins > 0) {
        await this.ledger.post({ userId, currency: 'COINS', amount: BigInt(opts.coins), type: 'ADMIN', source: `grant:${opts.batch}`, idempotencyKey: `grant:${opts.batch}:${userId}:m`, meta });
      }
    }
    return { players: poor.length };
  }
}
