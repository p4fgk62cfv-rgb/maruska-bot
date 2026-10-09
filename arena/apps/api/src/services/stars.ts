import { STAR_PACKS, starPack, type OwnerStarsDto, type StarOrderDto } from '@arena/shared';
import type { FastifyBaseLogger } from 'fastify';
import type { Db } from '../db.js';
import type { StarOrder } from '../generated/prisma/client.js';
import { AppError } from '../lib/errors.js';
import type { Ledger } from './ledger.js';
import type { Outbox, TelegramBot } from './notifier.js';
import { displayName } from './users.js';

const PREFIX = 'arena:';
/** Where the sweep of the bot's Star transactions has got to. */
const SWEEP_KEY = 'stars_sweep_offset';
/** Unpaid orders a player may have open within an hour (each one is an invoice link). */
const OPEN_LIMIT = 10;

export type PrecheckoutAnswer = { ok: true } | { ok: false; message: string };

export interface PaymentNotice {
  payload: string;
  telegramId: bigint;
  stars: number;
  chargeId: string;
}

const orderDto = (o: StarOrder): StarOrderDto => ({
  id: o.id,
  pack: o.pack,
  stars: o.stars,
  coins: o.coins,
  status: o.status,
  createdAt: o.createdAt.toISOString(),
  paidAt: o.paidAt?.toISOString() ?? null,
});

const orderId = (payload: string): string | null => {
  if (!payload.startsWith(PREFIX)) return null;
  const id = payload.slice(PREFIX.length);
  return /^[0-9a-f-]{36}$/.test(id) ? id : null;
};

/**
 * Coins for Telegram Stars. The player asks for an invoice link here, pays in Telegram's own form,
 * and the bot (which receives the payment updates) asks this service to check and then to credit
 * the order. Crediting is keyed by the order, so a repeated notice or the sweep never pays twice.
 */
export class StarsService {
  private timer: NodeJS.Timeout | null = null;
  private sweeping = false;

  constructor(
    private readonly deps: { db: Db; ledger: Ledger; bot: TelegramBot | null; outbox: Outbox; log: FastifyBaseLogger },
  ) {}

  packs() {
    return { enabled: this.deps.bot !== null, packs: STAR_PACKS };
  }

  async createOrder(userId: string, packKey: string): Promise<{ order: StarOrderDto; link: string }> {
    const { db, bot } = this.deps;
    const pack = starPack(packKey);
    if (!pack) throw new AppError('NOT_FOUND');
    if (!bot) throw new AppError('PAYMENTS_UNAVAILABLE');
    const open = await db.starOrder.count({ where: { userId, status: 'PENDING', createdAt: { gt: new Date(Date.now() - 3600_000) } } });
    if (open >= OPEN_LIMIT) throw new AppError('RATE_LIMITED');
    const order = await db.starOrder.create({ data: { userId, pack: pack.key, stars: pack.stars, coins: pack.coins } });
    const link = await bot.createStarsInvoice({
      title: `${pack.coins} монет`,
      description: `${pack.coins} монет для Маруська Арены: рубашки, рамки, смайлы и подсказки в игре.`,
      payload: `${PREFIX}${order.id}`,
      label: `${pack.coins} монет`,
      stars: pack.stars,
    });
    if (!link) {
      await db.starOrder.delete({ where: { id: order.id } });
      throw new AppError('PAYMENTS_UNAVAILABLE');
    }
    return { order: orderDto(order), link };
  }

  async order(userId: string, id: string): Promise<StarOrderDto> {
    const order = await this.deps.db.starOrder.findUnique({ where: { id } });
    if (!order || order.userId !== userId) throw new AppError('NOT_FOUND');
    return orderDto(order);
  }

  /** pre_checkout_query: may this payment go through? Telegram waits at most 10 s for the answer. */
  async precheckout(payload: string, telegramId: bigint, stars: number, currency: string): Promise<PrecheckoutAnswer> {
    const id = orderId(payload);
    const order = id ? await this.deps.db.starOrder.findUnique({ where: { id }, include: { user: { select: { telegramId: true, bannedAt: true } } } }) : null;
    if (!order || order.user.telegramId !== telegramId) return { ok: false, message: 'Счёт не найден. Откройте магазин в игре заново.' };
    if (order.status !== 'PENDING') return { ok: false, message: 'Этот счёт уже оплачен.' };
    if (currency !== 'XTR' || stars !== order.stars) return { ok: false, message: 'Сумма не совпадает со счётом. Откройте магазин в игре заново.' };
    if (order.user.bannedAt) return { ok: false, message: 'Аккаунт в игре заблокирован.' };
    return { ok: true };
  }

  /** successful_payment (or the sweep): credit the order once. Returns the order, null if unknown. */
  async paid(notice: PaymentNotice): Promise<{ order: StarOrderDto; userId: string; credited: boolean } | null> {
    const { db, ledger, log } = this.deps;
    const id = orderId(notice.payload);
    if (!id) return null;
    const result = await db.$transaction(async (tx) => {
      const order = await tx.starOrder.findUnique({ where: { id }, include: { user: { select: { telegramId: true } } } });
      if (!order) return null;
      if (order.status !== 'PENDING') return { order, credited: false };
      if (order.user.telegramId !== notice.telegramId || order.stars !== notice.stars) {
        log.error({ orderId: id, stars: notice.stars }, 'stars payment does not match its order');
        return { order, credited: false };
      }
      // Only one of two concurrent notices moves the order on.
      const moved = await tx.starOrder.updateMany({ where: { id, status: 'PENDING' }, data: { status: 'PAID', chargeId: notice.chargeId, paidAt: new Date() } });
      if (moved.count !== 1) return { order, credited: false };
      await ledger.postIn(tx, {
        userId: order.userId,
        currency: 'COINS',
        amount: BigInt(order.coins),
        type: 'STARS_PURCHASE',
        source: `stars:${order.id}`,
        idempotencyKey: `stars:${order.id}`,
        meta: { stars: order.stars, pack: order.pack },
      });
      return { order: await tx.starOrder.findUniqueOrThrow({ where: { id } }), credited: true };
    });
    if (!result) return null;
    if (result.credited) log.info({ orderId: id, stars: result.order.stars, coins: result.order.coins }, 'stars payment credited');
    return { order: orderDto(result.order), userId: result.order.userId, credited: result.credited };
  }

  /**
   * Telegram took the stars but the bot's notice never reached us (a restart, the arena down):
   * walk the bot's Star transactions and credit every paid order that is still waiting.
   */
  async sweep(): Promise<number> {
    const { db, bot, outbox, log } = this.deps;
    if (!bot || this.sweeping) return 0;
    this.sweeping = true;
    let credited = 0;
    try {
      const row = await db.setting.findUnique({ where: { key: SWEEP_KEY } });
      let offset = typeof row?.value === 'number' ? row.value : 0;
      for (let page = 0; page < 20; page++) {
        const list = await bot.starTransactions(offset);
        if (!list || list.length === 0) break;
        for (const t of list) {
          const payload = t.source?.type === 'user' ? t.source.invoice_payload : undefined;
          if (!payload?.startsWith(PREFIX) || !t.source?.user) continue;
          const done = await this.paid({ payload, telegramId: BigInt(t.source.user.id), stars: t.amount, chargeId: t.id });
          if (done?.credited) {
            credited++;
            log.warn({ orderId: done.order.id }, 'stars payment credited by the sweep');
            await outbox.enqueue(done.userId, 'stars', {
              text: `✅ Оплата получена: <b>+${done.order.coins} монет</b> на вашем счёте в Арене.`,
            });
          }
        }
        offset += list.length;
        await db.setting.upsert({ where: { key: SWEEP_KEY }, create: { key: SWEEP_KEY, value: offset }, update: { value: offset } });
        if (list.length < 100) break;
      }
    } catch (error) {
      log.error({ err: error }, 'stars sweep failed');
    } finally {
      this.sweeping = false;
    }
    return credited;
  }

  start(intervalMs = 10 * 60_000): void {
    if (this.timer || !this.deps.bot) return;
    this.timer = setInterval(() => void this.sweep(), intervalMs);
    this.timer.unref();
    void this.sweep();
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  // ── owner ──

  async ownerList(now = Date.now()): Promise<OwnerStarsDto> {
    const { db } = this.deps;
    const orders = await db.starOrder.findMany({
      where: { status: { in: ['PAID', 'REFUNDED'] } },
      orderBy: { paidAt: 'desc' },
      take: 50,
      include: { user: { select: { firstName: true, lastName: true, username: true } } },
    });
    const sum = async (since: Date | null) =>
      (await db.starOrder.aggregate({ _sum: { stars: true }, where: { status: 'PAID', ...(since ? { paidAt: { gte: since } } : {}) } }))._sum.stars ?? 0;
    const day = new Date(now);
    day.setUTCHours(0, 0, 0, 0);
    const [today, month, all, buyers] = await Promise.all([
      sum(day),
      sum(new Date(now - 30 * 86_400_000)),
      sum(null),
      db.starOrder.groupBy({ by: ['userId'], where: { status: 'PAID' } }).then((rows) => rows.length),
    ]);
    return {
      orders: orders.map((o) => ({ ...orderDto(o), userId: o.userId, name: displayName(o.user), refundedAt: o.refundedAt?.toISOString() ?? null })),
      totals: { today, month, all, buyers },
    };
  }

  /** Stars back to the buyer; the coins are taken back as far as the balance allows. */
  async refund(id: string): Promise<StarOrderDto> {
    const { db, ledger, bot, log } = this.deps;
    const order = await db.starOrder.findUnique({ where: { id }, include: { user: { select: { telegramId: true } } } });
    if (!order) throw new AppError('NOT_FOUND');
    if (order.status !== 'PAID' || !order.chargeId) throw new AppError('DUPLICATE_REQUEST');
    if (!bot || !(await bot.refundStars(order.user.telegramId, order.chargeId))) throw new AppError('PAYMENTS_UNAVAILABLE');
    const updated = await db.$transaction(async (tx) => {
      const wallet = await tx.wallet.findUnique({ where: { userId_currency: { userId: order.userId, currency: 'COINS' } } });
      const back = BigInt(Math.min(order.coins, Number(wallet?.balance ?? 0n)));
      if (back > 0n) {
        await ledger.postIn(tx, {
          userId: order.userId,
          currency: 'COINS',
          amount: -back,
          type: 'STARS_REFUND',
          source: `stars:${order.id}`,
          idempotencyKey: `stars-refund:${order.id}`,
          meta: { stars: order.stars },
        });
      }
      return tx.starOrder.update({ where: { id }, data: { status: 'REFUNDED', refundedAt: new Date() } });
    });
    log.warn({ orderId: id, stars: order.stars }, 'stars payment refunded');
    return orderDto(updated);
  }
}
