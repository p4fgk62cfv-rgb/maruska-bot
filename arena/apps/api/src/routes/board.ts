import type { LeaderboardBy, LeaderboardRowDto, SeasonDto } from '@arena/shared';
import type { FastifyInstance } from 'fastify';
import { z } from 'zod';
import { requireSession, sessionOf } from '../auth/plugin.js';
import type { Context } from '../context.js';
import type { Prisma } from '../generated/prisma/client.js';
import { toNumber } from '../lib/money.js';
import { publicUser } from '../services/users.js';

/** Доска почёта: rating, credits won and wins decide the position (in that order of ties). */
const ORDER: Record<LeaderboardBy, Prisma.ProfileOrderByWithRelationInput[]> = {
  rating: [{ rating: 'desc' }, { totalWinnings: 'desc' }, { gamesWon: 'desc' }],
  winnings: [{ totalWinnings: 'desc' }, { rating: 'desc' }, { gamesWon: 'desc' }],
  wins: [{ gamesWon: 'desc' }, { rating: 'desc' }, { totalWinnings: 'desc' }],
};

export async function boardRoutes(app: FastifyInstance, ctx: Context): Promise<void> {
  const { db } = ctx;
  const auth = { preHandler: requireSession(ctx.config.SESSION_SECRET) };

  app.post('/wallet/daily-credits', { ...auth, config: { rateLimit: { max: 10, timeWindow: '1 minute' } } }, async (request) => {
    const balance = await ctx.wallets.claimDailyCredits(sessionOf(request).sub);
    return { credits: balance };
  });

  app.get('/leaderboard', auth, async (request): Promise<LeaderboardRowDto[]> => {
    const { by } = z.object({ by: z.enum(['rating', 'winnings', 'wins']).default('rating') }).parse(request.query);
    const rows = await db.profile.findMany({
      where: { gamesPlayed: { gt: 0 }, user: { bannedAt: null, isBot: false } },
      orderBy: ORDER[by],
      take: 100,
      include: { user: true },
    });
    return rows.map((p, i) => ({
      ...publicUser(p.user, p),
      place: i + 1,
      totalWinnings: toNumber(p.totalWinnings),
      gamesWon: p.gamesWon,
    }));
  });

  app.get('/season', auth, async (request): Promise<SeasonDto | null> => {
    const now = new Date();
    const season = await db.season.findFirst({ where: { startsAt: { lte: now }, endsAt: { gt: now } }, orderBy: { startsAt: 'desc' } });
    if (!season) return null;
    const userId = sessionOf(request).sub;
    const [top, mine] = await Promise.all([
      db.seasonRating.findMany({
        where: { seasonId: season.id },
        orderBy: [{ rating: 'desc' }, { winnings: 'desc' }],
        take: 50,
        include: { user: { include: { profile: true } } },
      }),
      db.seasonRating.findUnique({ where: { seasonId_userId: { seasonId: season.id, userId } } }),
    ]);
    const above = mine ? await db.seasonRating.count({ where: { seasonId: season.id, rating: { gt: mine.rating } } }) : null;
    return {
      id: season.id,
      title: season.title,
      startsAt: season.startsAt.toISOString(),
      endsAt: season.endsAt.toISOString(),
      top: top
        .filter((r) => r.user.profile)
        .map((r, i) => ({ ...publicUser(r.user, r.user.profile!), place: i + 1, seasonRating: r.rating })),
      me: { place: above === null ? null : above + 1, seasonRating: mine?.rating ?? 0 },
    };
  });
}
