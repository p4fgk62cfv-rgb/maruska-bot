import type { Db } from '../db.js';
import { Prisma, type Currency } from '../generated/prisma/client.js';
import { AppError } from '../lib/errors.js';
import type { Ledger } from './ledger.js';

export interface SuspiciousPair {
  loser: { id: string; telegramId: string; name: string };
  winner: { id: string; telegramId: string; name: string };
  games: number;
  lostToWinner: number;
  gaveUp: number;
  credits: number;
}

/**
 * Integrity tools for moderators. Deliberately losing to pass credits to someone
 * (even for payment) is forbidden by the rules; this finds the typical pattern:
 * the same pair meets often, one side nearly always loses with a stake, often by
 * giving up, and the credits flow one way.
 */
export class ModerationService {
  /** userId → ban end (epoch ms) or null for a permanent ban. */
  private banned = new Map<string, number | null>();

  constructor(private readonly db: Db, private readonly ledger: Ledger) {}

  async loadBans(): Promise<void> {
    const rows = await this.db.user.findMany({
      where: { bannedAt: { not: null }, OR: [{ bannedUntil: null }, { bannedUntil: { gt: new Date() } }] },
      select: { id: true, bannedUntil: true },
    });
    this.banned = new Map(rows.map((r) => [r.id, r.bannedUntil?.getTime() ?? null]));
  }

  /** Checked on every request and socket: a ban works immediately, even for issued sessions. */
  isBanned(userId: string, now = Date.now()): boolean {
    if (!this.banned.has(userId)) return false;
    const until = this.banned.get(userId);
    if (until === null || until === undefined || until > now) return true;
    this.banned.delete(userId);
    return false;
  }

  async suspiciousPairs(days = 7, minGames = 5, minCredits = 1000): Promise<SuspiciousPair[]> {
    const rows = await this.db.$queryRaw<
      { a: string; b: string; games: bigint; lost: bigint; gave_up: bigint; flow: bigint | null }[]
    >(Prisma.sql`
      WITH g AS (
        SELECT gp.game_id, gp.user_id, gp.net, gp.outcome
        FROM arena.game_players gp
        JOIN arena.games gm ON gm.id = gp.game_id
        WHERE gm.status = 'FINISHED' AND gm.stake > 0
          AND gm.finished_at > now() - make_interval(days => ${days}::int)
      ),
      together AS (
        SELECT a.user_id AS a, b.user_id AS b,
          count(*) AS games,
          count(*) FILTER (WHERE a.net < 0 AND b.net > 0) AS lost,
          count(*) FILTER (WHERE a.net < 0 AND b.net > 0 AND a.outcome = 'LEFT') AS gave_up,
          sum(b.net) FILTER (WHERE a.net < 0 AND b.net > 0) AS flow
        FROM g a JOIN g b ON a.game_id = b.game_id AND a.user_id <> b.user_id
        GROUP BY a.user_id, b.user_id
      )
      SELECT a, b, games, lost, gave_up, flow FROM together
      WHERE games >= ${minGames}::int AND lost >= 0.8 * games AND coalesce(flow, 0) >= ${minCredits}::bigint
      ORDER BY flow DESC
      LIMIT 50`);
    if (!rows.length) return [];
    const users = await this.db.user.findMany({ where: { id: { in: rows.flatMap((r) => [r.a, r.b]) } } });
    const who = (id: string) => {
      const u = users.find((x) => x.id === id)!;
      return { id, telegramId: u.telegramId.toString(), name: [u.firstName, u.lastName].filter(Boolean).join(' ') };
    };
    return rows.map((r) => ({
      loser: who(r.a),
      winner: who(r.b),
      games: Number(r.games),
      lostToWinner: Number(r.lost),
      gaveUp: Number(r.gave_up),
      credits: Number(r.flow ?? 0n),
    }));
  }

  /** `days` null = permanent (repeat offence). Returns the user id. */
  async ban(telegramId: bigint, days: number | null, reason: string): Promise<string> {
    const user = await this.db.user.update({
      where: { telegramId },
      data: { bannedAt: new Date(), bannedUntil: days ? new Date(Date.now() + days * 86_400_000) : null, banReason: reason.slice(0, 255) },
    });
    this.banned.set(user.id, user.bannedUntil?.getTime() ?? null);
    return user.id;
  }

  async unban(telegramId: bigint): Promise<void> {
    const user = await this.db.user.update({ where: { telegramId }, data: { bannedAt: null, bannedUntil: null, banReason: null } });
    this.banned.delete(user.id);
  }

  /**
   * Takes back credits or coins obtained against the rules. Never drives a balance below
   * zero; `requestId` makes a retried moderator action a no-op. Returns the amount taken.
   */
  async clawback(telegramId: bigint, currency: Currency, amount: number, reason: string, requestId: string): Promise<number> {
    const user = await this.db.user.findUnique({ where: { telegramId } });
    if (!user) throw new AppError('NOT_FOUND');
    return this.db.$transaction(async (tx) => {
      const wallet = await tx.wallet.findUniqueOrThrow({ where: { userId_currency: { userId: user.id, currency } } });
      const take = BigInt(Math.min(amount, Number(wallet.balance)));
      if (take <= 0n) return 0;
      const posted = await this.ledger.postIn(tx, {
        userId: user.id,
        currency,
        amount: -take,
        type: 'MODERATION',
        source: 'moderation',
        idempotencyKey: `mod:${requestId}`,
        meta: { reason },
      });
      return posted.duplicate ? 0 : Number(take);
    });
  }
}
