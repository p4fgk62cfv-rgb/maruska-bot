import type { AchievementDto, ItemDto, ServerDto, TransactionDto } from '@arena/shared';
import { GAME_SERVERS } from '@arena/shared';
import type { FastifyInstance } from 'fastify';
import { z } from 'zod';
import { requireSession, sessionOf } from '../auth/plugin.js';
import type { Context } from '../context.js';
import { AppError } from '../lib/errors.js';
import { toNumber } from '../lib/money.js';

const AVATAR_MAX_BYTES = 200 * 1024;
/** Letters, digits, spaces, a little punctuation and emoji — no markup, no control characters. */
const NICKNAME = /^[\p{L}\p{N}\p{Extended_Pictographic}‍️ ._\-@!?~*'"()+=&#№]+$/u;
/** Names that pose as staff or the bot. */
const RESERVED = /(admin|админ|moder|модер|support|поддержк|маруськ|maruska|arena|арена)/i;

/** Trusts the bytes, not the declared type. */
function sniffImage(data: Buffer): 'image/jpeg' | 'image/png' | 'image/webp' | null {
  if (data.length > 3 && data[0] === 0xff && data[1] === 0xd8 && data[2] === 0xff) return 'image/jpeg';
  if (data.length > 8 && data.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) return 'image/png';
  if (data.length > 12 && data.toString('ascii', 0, 4) === 'RIFF' && data.toString('ascii', 8, 12) === 'WEBP') return 'image/webp';
  return null;
}

const pageSchema = z.object({ limit: z.coerce.number().int().min(1).max(100).default(30) });

export async function profileRoutes(app: FastifyInstance, ctx: Context): Promise<void> {
  const { db } = ctx;
  const auth = { preHandler: requireSession(ctx.config.SESSION_SECRET) };

  app.get('/me', auth, async (request) => {
    const me = await ctx.users.me(sessionOf(request).sub);
    if (!me) throw new AppError('UNAUTHORIZED');
    return me;
  });

  /** «Имя в игре»: 2–20 characters; empty brings the Telegram name back. */
  app.put('/me/nickname', { ...auth, config: { rateLimit: { max: 10, timeWindow: '1 minute' } } }, async (request) => {
    const userId = sessionOf(request).sub;
    const raw = z.object({ nickname: z.string().max(64) }).parse(request.body).nickname;
    const nickname = raw.replace(/\s+/g, ' ').trim();
    if (nickname && (nickname.length < 2 || nickname.length > 20 || !NICKNAME.test(nickname) || RESERVED.test(nickname))) {
      throw new AppError('VALIDATION_FAILED');
    }
    await db.profile.update({ where: { userId }, data: { nickname: nickname || null } });
    const me = await ctx.users.me(userId);
    return me;
  });

  /** «Загрузить аватарку»: the app sends a small square picture (resized on the phone). */
  app.post('/me/avatar', { ...auth, bodyLimit: 400 * 1024, config: { rateLimit: { max: 5, timeWindow: '1 minute' } } }, async (request) => {
    const userId = sessionOf(request).sub;
    const { image } = z.object({ image: z.string().max(380_000) }).parse(request.body);
    const match = /^data:(image\/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=]+)$/.exec(image);
    if (!match) throw new AppError('VALIDATION_FAILED');
    const data = Buffer.from(match[2]!, 'base64');
    const mime = sniffImage(data);
    if (!mime || data.length > AVATAR_MAX_BYTES) throw new AppError('VALIDATION_FAILED');
    await db.$transaction([
      db.userAvatar.upsert({ where: { userId }, create: { userId, mime, data }, update: { mime, data } }),
      db.profile.update({ where: { userId }, data: { avatarVersion: { increment: 1 } } }),
    ]);
    // A null version cannot be incremented: start from 1.
    await db.profile.updateMany({ where: { userId, avatarVersion: null }, data: { avatarVersion: 1 } });
    return ctx.users.me(userId);
  });

  app.delete('/me/avatar', auth, async (request) => {
    const userId = sessionOf(request).sub;
    await db.$transaction([
      db.userAvatar.deleteMany({ where: { userId } }),
      db.profile.update({ where: { userId }, data: { avatarVersion: null } }),
    ]);
    return ctx.users.me(userId);
  });

  /** Public: <img> tags cannot send a token. URLs carry a version, so they are cached for good. */
  app.get('/avatars/:userId', async (request, reply) => {
    const { userId } = z.object({ userId: z.uuid() }).parse(request.params);
    const avatar = await db.userAvatar.findUnique({ where: { userId } });
    if (!avatar) throw new AppError('NOT_FOUND');
    return reply
      .type(avatar.mime)
      .header('cache-control', 'public, max-age=31536000, immutable')
      .header('x-content-type-options', 'nosniff')
      .send(Buffer.from(avatar.data));
  });

  /** Link to the Mini App for «Поделиться». */
  app.get('/app-link', auth, async () => {
    const { BOT_USERNAME, MINI_APP_SHORT_NAME } = ctx.config;
    return { link: MINI_APP_SHORT_NAME ? `https://t.me/${BOT_USERNAME}/${MINI_APP_SHORT_NAME}` : `https://t.me/${BOT_USERNAME}` };
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
