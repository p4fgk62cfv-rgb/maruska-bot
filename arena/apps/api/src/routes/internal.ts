import { timingSafeEqual } from 'node:crypto';
import { ratingBadge } from '@arena/shared';
import type { FastifyInstance, FastifyRequest } from 'fastify';
import { z } from 'zod';
import type { Context } from '../context.js';
import { createTournamentSchema } from '../services/tournaments.js';
import { AppError } from '../lib/errors.js';
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

  /** What is going on right now — for a bot status line or the admin panel. */
  app.get('/internal/stats', { preHandler: check }, async () => ({
    online: ctx.realtime.hub.onlineUsers().length,
    games: ctx.realtime.games.count(),
    openRooms: ctx.realtime.rooms.list().filter((r) => r.status === 'waiting' && !r.isPrivate).length,
  }));
}
