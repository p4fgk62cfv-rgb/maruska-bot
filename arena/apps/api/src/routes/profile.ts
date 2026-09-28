import type { AchievementDto, ItemDto, ServerDto, TransactionDto } from '@arena/shared';
import { GAME_SERVERS } from '@arena/shared';
import type { FastifyInstance } from 'fastify';
import { z } from 'zod';
import { requireSession, sessionOf } from '../auth/plugin.js';
import type { Context } from '../context.js';
import { AppError } from '../lib/errors.js';
import { toNumber } from '../lib/money.js';

const pageSchema = z.object({ limit: z.coerce.number().int().min(1).max(100).default(30) });

export async function profileRoutes(app: FastifyInstance, ctx: Context): Promise<void> {
  const { db } = ctx;
  const auth = { preHandler: requireSession(ctx.config.SESSION_SECRET) };

  app.get('/me', auth, async (request) => {
    const me = await ctx.users.me(sessionOf(request).sub);
    if (!me) throw new AppError('UNAUTHORIZED');
    return me;
  });

  app.get('/profile', auth, async (request) => {
    const me = await ctx.users.me(sessionOf(request).sub);
    if (!me) throw new AppError('UNAUTHORIZED');
    return me;
  });

  app.get('/profile/:userId', auth, async (request) => {
    const { userId } = z.object({ userId: z.uuid() }).parse(request.params);
    const profile = await ctx.users.publicProfile(userId);
    if (!profile) throw new AppError('NOT_FOUND');
    return profile;
  });

  app.get('/wallet/transactions', auth, async (request): Promise<TransactionDto[]> => {
    const { limit } = pageSchema.parse(request.query);
    const rows = await db.transaction.findMany({
      where: { userId: sessionOf(request).sub },
      orderBy: { createdAt: 'desc' },
      take: limit,
    });
    return rows.map((t) => ({
      id: t.id,
      currency: t.currency,
      amount: toNumber(t.amount),
      type: t.type,
      source: t.source,
      balanceBefore: toNumber(t.balanceBefore),
      balanceAfter: toNumber(t.balanceAfter),
      createdAt: t.createdAt.toISOString(),
    }));
  });

  app.get('/servers', auth, async (): Promise<ServerDto[]> => {
    const online = await ctx.presence.onlineByServer();
    return GAME_SERVERS.map((s) => ({ ...s, online: online[s.key] ?? 0 }));
  });

  app.get('/achievements', auth, async (request): Promise<AchievementDto[]> => {
    const userId = sessionOf(request).sub;
    const rows = await db.achievement.findMany({
      orderBy: { sortOrder: 'asc' },
      include: { users: { where: { userId } } },
    });
    return rows.map((a) => ({
      key: a.key,
      title: a.title,
      description: a.description,
      icon: a.icon,
      goal: a.goal,
      progress: a.users[0]?.progress ?? 0,
      unlockedAt: a.users[0]?.unlockedAt?.toISOString() ?? null,
    }));
  });

  app.get('/items', auth, async (request): Promise<ItemDto[]> => ctx.items.list(sessionOf(request).sub));

  const itemParam = z.object({ key: z.string().regex(/^[a-z0-9_]{2,64}$/) });
  app.post('/items/:key/buy', auth, async (request) => {
    await ctx.items.buy(sessionOf(request).sub, itemParam.parse(request.params).key);
    return ctx.items.list(sessionOf(request).sub);
  });
  app.post('/items/:key/equip', auth, async (request) => ctx.items.equip(sessionOf(request).sub, itemParam.parse(request.params).key));
  app.post('/items/:key/unequip', auth, async (request) => ctx.items.unequip(sessionOf(request).sub, itemParam.parse(request.params).key));
}
