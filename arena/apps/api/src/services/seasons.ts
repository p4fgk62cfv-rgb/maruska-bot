import type { FastifyBaseLogger } from 'fastify';
import type { Config } from '../config.js';
import type { Db } from '../db.js';
import type { Season } from '../generated/prisma/client.js';
import type { Ledger } from './ledger.js';
import type { Outbox } from './notifier.js';

const MOSCOW_MS = 3 * 3600_000;
const DAY = 86_400_000;
const MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];

/** «100000,50000,10000x3» → [100000, 50000, 10000, 10000, 10000]. Junk parts are skipped. */
export function parsePlaces(spec: string): number[] {
  const out: number[] = [];
  for (const part of spec.split(',')) {
    if (!part.trim()) continue;
    const [value, times] = part.trim().split('x');
    const amount = Number(value);
    const count = times === undefined ? 1 : Number(times);
    if (!Number.isInteger(amount) || amount < 0 || !Number.isInteger(count) || count < 1 || count > 100) continue;
    for (let i = 0; i < count; i++) out.push(amount);
  }
  return out;
}

/** The Moscow calendar month around a moment: its bounds in UTC and a title («Октябрь 2026»). */
export function moscowMonth(now: Date): { start: Date; end: Date; title: string } {
  const msk = new Date(now.getTime() + MOSCOW_MS);
  const y = msk.getUTCFullYear();
  const m = msk.getUTCMonth();
  return {
    start: new Date(Date.UTC(y, m, 1) - MOSCOW_MS),
    end: new Date(Date.UTC(y, m + 1, 1) - MOSCOW_MS),
    title: `${MONTHS[m]} ${y}`,
  };
}

/**
 * Monthly seasons.
 *
 * Every month (Moscow time) a season starts by itself, unless the admin already set one up for
 * these dates. When a season ends, the top of its rating gets credits and VIP days; the season is
 * marked rewarded in the same transaction, and every payment has its own idempotency key, so a
 * restart or two servers at once never pay twice.
 */
export class SeasonService {
  private timer: NodeJS.Timeout | null = null;

  constructor(
    private readonly deps: {
      config: Config;
      db: Db;
      ledger: Ledger;
      outbox: Outbox;
      log: FastifyBaseLogger;
    },
  ) {}

  private get db(): Db {
    return this.deps.db;
  }

  start(intervalMs = 300_000): void {
    void this.tick().catch((e) => this.fail(e));
    this.timer = setInterval(() => void this.tick().catch((e) => this.fail(e)), intervalMs);
    this.timer.unref();
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
  }

  private fail(error: unknown): void {
    this.deps.log.error({ err: error }, 'season job failed');
  }

  async tick(now = new Date()): Promise<void> {
    if (this.deps.config.AUTO_SEASONS !== 'on') return;
    await this.payEnded(now);
    await this.ensureCurrent(now);
  }

  /** Starts this month's season if no season covers the moment. Never overlaps a season the admin created. */
  async ensureCurrent(now = new Date()): Promise<Season | null> {
    const current = await this.db.season.findFirst({ where: { startsAt: { lte: now }, endsAt: { gt: now } } });
    if (current) return null;
    const month = moscowMonth(now);
    const before = await this.db.season.findFirst({ where: { endsAt: { lte: now } }, orderBy: { endsAt: 'desc' } });
    const after = await this.db.season.findFirst({ where: { startsAt: { gt: now } }, orderBy: { startsAt: 'asc' } });
    const startsAt = before && before.endsAt > month.start ? before.endsAt : month.start;
    const endsAt = after && after.startsAt < month.end ? after.startsAt : month.end;
    if (endsAt <= startsAt) return null;
    const season = await this.db.season.create({ data: { title: `Сезон «${month.title}»`, startsAt, endsAt } });
    this.deps.log.info({ seasonId: season.id, startsAt, endsAt }, 'season started');
    return season;
  }

  async payEnded(now = new Date()): Promise<void> {
    const ended = await this.db.season.findMany({ where: { endsAt: { lte: now }, rewarded: false }, orderBy: { endsAt: 'asc' } });
    for (const season of ended) await this.pay(season);
  }

  /** Pays the top of an ended season. Returns how many players got a prize. */
  async pay(season: Season): Promise<number> {
    const credits = parsePlaces(this.deps.config.SEASON_PRIZES);
    const vip = parsePlaces(this.deps.config.SEASON_VIP_DAYS);
    const places = Math.max(credits.length, vip.length);
    const top = places
      ? await this.db.seasonRating.findMany({
          where: { seasonId: season.id, rating: { gt: 0 }, user: { isBot: false, bannedAt: null } },
          orderBy: [{ rating: 'desc' }, { wins: 'desc' }, { winnings: 'desc' }],
          take: places,
        })
      : [];

    const paid = await this.db.$transaction(async (tx) => {
      const claimed = await tx.season.updateMany({ where: { id: season.id, rewarded: false }, data: { rewarded: true } });
      if (!claimed.count) return [];
      const winners: { userId: string; place: number; credits: number; days: number }[] = [];
      for (const [i, row] of top.entries()) {
        const amount = credits[i] ?? 0;
        const days = vip[i] ?? 0;
        if (amount > 0) {
          await this.deps.ledger.postIn(tx, {
            userId: row.userId,
            currency: 'CREDITS',
            amount: BigInt(amount),
            type: 'SEASON_REWARD',
            source: `season:${season.id}`,
            idempotencyKey: `season:${season.id}:${row.userId}`,
            meta: { place: i + 1 },
          });
        }
        if (days > 0) {
          const profile = await tx.profile.findUnique({ where: { userId: row.userId }, select: { premiumUntil: true } });
          if (profile) {
            const from = Math.max(Date.now(), profile.premiumUntil?.getTime() ?? 0);
            await tx.profile.update({ where: { userId: row.userId }, data: { premiumUntil: new Date(from + days * DAY) } });
          }
        }
        winners.push({ userId: row.userId, place: i + 1, credits: amount, days });
      }
      return winners;
    });

    for (const w of paid) {
      const parts = [w.credits ? `${w.credits.toLocaleString('ru-RU')} 🪙` : '', w.days ? `VIP на ${w.days} дн. 👑` : ''].filter(Boolean);
      await this.deps.outbox
        .enqueue(w.userId, 'season_reward', {
          text: `🏆 <b>${season.title}</b> завершён!\nВы заняли <b>${w.place}-е место</b>. Награда: ${parts.join(' и ')}.\nНовый сезон уже начался — удачи!`,
        })
        .catch((error: unknown) => this.deps.log.warn({ err: error, userId: w.userId }, 'season reward message not queued'));
    }
    if (paid.length || top.length === 0) this.deps.log.info({ seasonId: season.id, winners: paid.length }, 'season rewarded');
    return paid.length;
  }
}
