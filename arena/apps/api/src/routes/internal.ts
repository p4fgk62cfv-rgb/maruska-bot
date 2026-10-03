import { timingSafeEqual } from 'node:crypto';
import { ratingBadge } from '@arena/shared';
import type { FastifyInstance, FastifyRequest } from 'fastify';
import { z } from 'zod';
import type { Context } from '../context.js';
import { createTournamentSchema } from '../services/tournaments.js';
import { adminRoutes } from './admin.js';
import { AppError } from '../lib/errors.js';
import { metrics } from '../lib/metrics.js';
import { toNumber } from '../lib/money.js';

/**
 * Bot → arena API. Called by the Python bot with `Authorization: Bearer <INTERNAL_API_SECRET>`.
 * Disabled (404) when the secret is not configured.
 */
export async function internalRoutes(app: FastifyInstance, ctx: Context): Promise<void> {
  const secret = ctx.config.INTERNAL_API_SECRET;
  if (!secret) return;

  const check = async (request: FastifyRequest) => {
    const given = Buffer.from(request.headers.authorization?.replace(/^Bearer /, '') ?? '');
    const expected = Buffer.from(secret);
    if (given.length !== expected.length || !timingSafeEqual(given, expected)) throw new AppError('UNAUTHORIZED');
  };

  await adminRoutes(app, ctx, check);

  /** Arena card for the bot's /profile: rating, league, wins. */
  app.get('/internal/players/:telegramId', { preHandler: check }, async (request) => {
    const { telegramId } = z.object({ telegramId: z.coerce.bigint() }).parse(request.params);
    const user = await ctx.db.user.findUnique({ where: { telegramId }, include: { profile: true } });
    if (!user?.profile) throw new AppError('NOT_FOUND');
    const badge = ratingBadge(user.profile.rating);
    return {
      rating: user.profile.rating,
      league: badge.league.name,
      level: badge.level,
      gamesPlayed: user.profile.gamesPlayed,
      gamesWon: user.profile.gamesWon,
      totalWinnings: toNumber(user.profile.totalWinnings),
    };
  });

  /** Owner tools (bot admin panel): announce a tournament. */
  app.post('/internal/tournaments', { preHandler: check }, async (request) => {
    const id = await ctx.tournaments.create(createTournamentSchema.parse(request.body));
    return { id };
  });

  // ── moderation ──
  const byTelegram = z.object({ telegramId: z.coerce.bigint() });

  app.get('/internal/integrity/suspicious', { preHandler: check }, async (request) => {
    const q = z
      .object({
        days: z.coerce.number().int().min(1).max(90).default(7),
        minGames: z.coerce.number().int().min(2).default(5),
        minCredits: z.coerce.number().int().min(0).default(1000),
        /** Only pairs with this player (Telegram ID). */
        telegramId: z.coerce.bigint().optional(),
      })
      .parse(request.query);
    const user = q.telegramId ? await ctx.db.user.findUnique({ where: { telegramId: q.telegramId }, select: { id: true } }) : null;
    if (q.telegramId && !user) return [];
    return ctx.moderation.suspiciousPairs(q.days, q.minGames, q.minCredits, user?.id);
  });

  app.post('/internal/moderation/ban', { preHandler: check }, async (request) => {
    const body = byTelegram.extend({ days: z.number().int().positive().nullable().default(null), reason: z.string().min(1).max(255) }).parse(request.body);
    const userId = await ctx.moderation.ban(body.telegramId, body.days, body.reason);
    await ctx.realtime.expel(userId);
    return { ok: true };
  });

  app.post('/internal/moderation/unban', { preHandler: check }, async (request) => {
    await ctx.moderation.unban(byTelegram.parse(request.body).telegramId);
    return { ok: true };
  });

  app.post('/internal/moderation/clawback', { preHandler: check }, async (request) => {
    const body = byTelegram
      .extend({ currency: z.enum(['CREDITS', 'COINS']), amount: z.number().int().positive(), reason: z.string().min(1).max(255), requestId: z.string().min(8).max(64) })
      .parse(request.body);
    const taken = await ctx.moderation.clawback(body.telegramId, body.currency, body.amount, body.reason, body.requestId);
    return { taken };
  });

  /** «Пожаловаться» from the table: players with the most distinct reporters first. */
  app.get('/internal/moderation/reports', { preHandler: check }, async (request) => {
    const { days } = z.object({ days: z.coerce.number().int().min(1).max(90).default(7) }).parse(request.query);
    const since = new Date(Date.now() - days * 86_400_000);
    const rows = await ctx.db.playerReport.findMany({
      where: { createdAt: { gt: since } },
      select: { targetId: true, reporterId: true, reason: true, target: { select: { telegramId: true, username: true, firstName: true } } },
    });
    const byTarget = new Map<string, { telegramId: string; name: string; reporters: Set<string>; reasons: Record<string, number> }>();
    for (const r of rows) {
      const entry = byTarget.get(r.targetId) ?? {
        telegramId: r.target.telegramId.toString(),
        name: r.target.username ? `@${r.target.username}` : r.target.firstName,
        reporters: new Set<string>(),
        reasons: {},
      };
      entry.reporters.add(r.reporterId);
      entry.reasons[r.reason] = (entry.reasons[r.reason] ?? 0) + 1;
      byTarget.set(r.targetId, entry);
    }
    return [...byTarget.values()]
      .map((e) => ({ telegramId: e.telegramId, name: e.name, reporters: e.reporters.size, reasons: e.reasons }))
      .sort((a, b) => b.reporters - a.reporters);
  });

  /** Prometheus scrape target. */
  app.get('/internal/metrics', { preHandler: check }, async (_request, reply) => {
    const rooms = ctx.realtime.rooms.list();
    const outbox = await ctx.db.notification.count({ where: { sentAt: null, attempts: { lt: 5 } } });
    reply.type('text/plain; version=0.0.4');
    return metrics.render({
      arena_ws_online: { help: 'Connected players', value: ctx.realtime.hub.onlineUsers().length },
      arena_games_running: { help: 'Games in memory', value: ctx.realtime.games.count() },
      arena_rooms_waiting: { help: 'Rooms waiting for players', value: rooms.filter((r) => r.status === 'waiting').length },
      arena_outbox_pending: { help: 'Bot messages not yet delivered', value: outbox },
      arena_snapshot_backlog: { help: 'Snapshot writes waiting for a retry', value: ctx.realtime.storeBacklog() },
      arena_moves_backlog: { help: 'Logged moves waiting for a retry', value: ctx.realtime.games.movesBacklog() },
    });
  });

  /** What is going on right now — for a bot status line or the admin panel. */
  app.get('/internal/stats', { preHandler: check }, async () => ({
    online: ctx.realtime.hub.onlineUsers().length,
    games: ctx.realtime.games.count(),
    openRooms: ctx.realtime.rooms.list().filter((r) => r.status === 'waiting' && !r.isPrivate).length,
  }));
}
