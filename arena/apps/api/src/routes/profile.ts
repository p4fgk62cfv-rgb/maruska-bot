import type { AchievementDto, FriendDto, ItemDto, ServerDto, TournamentDto, TransactionDto } from '@arena/shared';
import { GAME_SERVERS } from '@arena/shared';
import type { FastifyInstance } from 'fastify';
import { z } from 'zod';
import { requireSession, sessionOf } from '../auth/plugin.js';
import type { Context } from '../context.js';
import { AppError } from '../lib/errors.js';
import { toNumber } from '../lib/money.js';
import { publicUser } from '../services/users.js';

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

  app.get('/items', auth, async (request): Promise<ItemDto[]> => {
    const userId = sessionOf(request).sub;
    const rows = await db.item.findMany({
      where: { isActive: true },
      orderBy: { sortOrder: 'asc' },
      include: { owners: { where: { userId } } },
    });
    return rows.map((i) => ({
      key: i.key,
      kind: i.kind,
      name: i.name,
      rarity: i.rarity,
      price: toNumber(i.price),
      currency: i.currency,
      owned: i.price === 0n || i.owners.length > 0,
      equipped: i.owners[0]?.equipped ?? false,
    }));
  });

  app.get('/friends', auth, async (request): Promise<FriendDto[]> => {
    const rows = await db.friend.findMany({
      where: { userId: sessionOf(request).sub },
      include: { friend: { include: { profile: true } } },
      take: 200,
    });
    const presence = await ctx.presence.lookup(rows.map((r) => r.friendId));
    return rows
      .filter((r) => r.friend.profile)
      .map((r) => ({ ...publicUser(r.friend, r.friend.profile!), presence: presence[r.friendId] ?? 'offline' }));
  });

  app.get('/tournaments', auth, async (request): Promise<TournamentDto[]> => {
    const { status } = z.object({ status: z.enum(['active', 'finished']).default('active') }).parse(request.query);
    const rows = await db.tournament.findMany({
      where: { status: status === 'active' ? { in: ['ANNOUNCED', 'REGISTRATION', 'RUNNING'] } : { in: ['FINISHED', 'CANCELLED'] } },
      orderBy: { startsAt: status === 'active' ? 'asc' : 'desc' },
      include: { _count: { select: { players: true } } },
      take: 50,
    });
    return rows.map((t) => ({
      id: t.id,
      title: t.title,
      status: t.status,
      prizePool: toNumber(t.prizePool),
      entryFee: toNumber(t.entryFee),
      currency: t.currency,
      players: t._count.players,
      maxPlayers: t.maxPlayers,
      startsAt: t.startsAt.toISOString(),
    }));
  });
}
