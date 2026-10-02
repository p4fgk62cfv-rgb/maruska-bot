import type { PlayerCardDto, ReportReasonDto } from '@arena/shared';
import { isPremium } from '@arena/shared';
import type { FastifyInstance } from 'fastify';
import { z } from 'zod';
import { requireSession, sessionOf } from '../auth/plugin.js';
import type { Context } from '../context.js';
import type { ReportReason } from '../generated/prisma/client.js';
import { AppError } from '../lib/errors.js';
import { toNumber } from '../lib/money.js';
import { publicUser } from '../services/users.js';

const userParam = z.object({ userId: z.uuid() });
const REASON: Record<ReportReasonDto, ReportReason> = { cheating: 'CHEATING', collusion: 'COLLUSION', insult: 'INSULT', other: 'OTHER' };
/** One report per reporter and player a day is enough: repeats are accepted but not stored. */
const REPORT_COOLDOWN_MS = 24 * 3600_000;
const BADGES = 8;

/** Opponent cards at the table: stats, badges, «В друзья», «Пожаловаться» and a private label. */
export async function playerRoutes(app: FastifyInstance, ctx: Context): Promise<void> {
  const { db } = ctx;
  const auth = { preHandler: requireSession(ctx.config.SESSION_SECRET) };

  app.get('/players/:userId/card', auth, async (request): Promise<PlayerCardDto> => {
    const me = sessionOf(request).sub;
    const { userId } = userParam.parse(request.params);
    const now = new Date();
    const [user, season, badges, equipped, relations, note] = await Promise.all([
      db.user.findUnique({ where: { id: userId }, include: { profile: true } }),
      db.season.findFirst({ where: { startsAt: { lte: now }, endsAt: { gt: now } }, include: { ratings: { where: { userId } } } }),
      db.userAchievement.findMany({
        where: { userId, unlockedAt: { not: null } },
        orderBy: { unlockedAt: 'desc' },
        take: BADGES,
        include: { achievement: { select: { key: true, title: true, icon: true } } },
      }),
      ctx.items.equipped(userId),
      ctx.friends.relations(me, [userId]),
      db.playerNote.findUnique({ where: { ownerId_targetId: { ownerId: me, targetId: userId } } }),
    ]);
    const profile = user?.profile;
    if (!user || !profile) throw new AppError('NOT_FOUND');
    const decided = profile.gamesWon + profile.gamesLost;
    const inSeason = season?.ratings[0];
    return {
      ...publicUser(user, profile),
      frame: equipped.frame,
      crown: equipped.crown,
      premium: isPremium(profile.premiumUntil?.getTime() ?? null, now.getTime()),
      season: season
        ? { title: season.title, rating: inSeason?.rating ?? 0, winnings: toNumber(inSeason?.winnings ?? 0n), wins: inSeason?.wins ?? 0 }
        : null,
      total: {
        rating: profile.rating,
        winnings: toNumber(profile.totalWinnings),
        wins: profile.gamesWon,
        games: profile.gamesPlayed,
        winRate: decided ? Math.round((profile.gamesWon / decided) * 100) : 0,
      },
      achievements: badges.map((b) => b.achievement),
      relation: relations[userId] ?? 'none',
      note: note?.text ?? null,
      bot: user.isBot,
    };
  });

  /** The full game card: stats, favourite kind of game, history, rare titles, games together. */
  app.get('/players/:userId/profile', auth, async (request) => {
    const { userId } = userParam.parse(request.params);
    return ctx.profiles.profile(sessionOf(request).sub, userId);
  });

  /** «История матчей», page by page (newest first). */
  app.get('/players/:userId/matches', auth, async (request) => {
    const { userId } = userParam.parse(request.params);
    const { limit, before } = z
      .object({ limit: z.coerce.number().int().min(1).max(50).default(20), before: z.iso.datetime().optional() })
      .parse(request.query);
    return ctx.profiles.matches(userId, limit, before ? new Date(before) : undefined);
  });

  app.put('/players/:userId/favorite', { ...auth, config: { rateLimit: { max: 30, timeWindow: '1 minute' } } }, async (request) =>
    ctx.friends.setFavorite(sessionOf(request).sub, userParam.parse(request.params).userId, true),
  );
  app.delete('/players/:userId/favorite', auth, async (request) =>
    ctx.friends.setFavorite(sessionOf(request).sub, userParam.parse(request.params).userId, false),
  );

  /** My labels for the people at my table, to show under their portraits. */
  app.get('/players/notes', auth, async (request): Promise<Record<string, string>> => {
    const me = sessionOf(request).sub;
    const { ids } = z
      .object({ ids: z.preprocess((v) => (typeof v === 'string' && v ? v.split(',') : []), z.array(z.uuid()).max(6)) })
      .parse(request.query);
    if (!ids.length) return {};
    const rows = await db.playerNote.findMany({ where: { ownerId: me, targetId: { in: ids } } });
    return Object.fromEntries(rows.map((r) => [r.targetId, r.text]));
  });

  app.put('/players/:userId/note', { ...auth, config: { rateLimit: { max: 30, timeWindow: '1 minute' } } }, async (request) => {
    const me = sessionOf(request).sub;
    const { userId } = userParam.parse(request.params);
    const { text } = z.object({ text: z.string().max(40) }).parse(request.body);
    const clean = text.replace(/\s+/g, ' ').trim();
    if (userId === me) throw new AppError('VALIDATION_FAILED');
    if (!clean) {
      await db.playerNote.deleteMany({ where: { ownerId: me, targetId: userId } });
      return { note: null };
    }
    const exists = await db.user.count({ where: { id: userId } });
    if (!exists) throw new AppError('NOT_FOUND');
    await db.playerNote.upsert({
      where: { ownerId_targetId: { ownerId: me, targetId: userId } },
      create: { ownerId: me, targetId: userId, text: clean },
      update: { text: clean },
    });
    return { note: clean };
  });

  app.post('/players/:userId/report', { ...auth, config: { rateLimit: { max: 10, timeWindow: '1 minute' } } }, async (request) => {
    const me = sessionOf(request).sub;
    const { userId } = userParam.parse(request.params);
    const body = z
      .object({ reason: z.enum(['cheating', 'collusion', 'insult', 'other']), gameId: z.uuid().optional() })
      .parse(request.body);
    if (userId === me) throw new AppError('VALIDATION_FAILED');
    const exists = await db.user.count({ where: { id: userId } });
    if (!exists) throw new AppError('NOT_FOUND');
    const recent = await db.playerReport.count({
      where: { reporterId: me, targetId: userId, createdAt: { gt: new Date(Date.now() - REPORT_COOLDOWN_MS) } },
    });
    if (!recent) await db.playerReport.create({ data: { reporterId: me, targetId: userId, gameId: body.gameId ?? null, reason: REASON[body.reason] } });
    return { ok: true };
  });
}
