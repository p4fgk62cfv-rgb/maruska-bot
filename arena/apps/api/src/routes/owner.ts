import type { AnnouncementDto, OwnerPlayerDto, WelcomeGiftDto } from '@arena/shared';
import type { FastifyInstance, FastifyRequest } from 'fastify';
import { z } from 'zod';
import { requireSession, sessionOf } from '../auth/plugin.js';
import type { Context } from '../context.js';
import type { Prisma } from '../generated/prisma/client.js';
import { AppError } from '../lib/errors.js';
import { toNumber } from '../lib/money.js';
import { avatarUrl, displayName } from '../services/users.js';

const userParam = z.object({ userId: z.uuid() });

/**
 * «Управление» inside the game, for the owners listed in OWNER_IDS only: the pop-up everyone sees
 * on the start screen, and gifts of credits, coins and items to any player.
 */
export async function ownerRoutes(app: FastifyInstance, ctx: Context): Promise<void> {
  const { db } = ctx;
  const session = requireSession(ctx.config.SESSION_SECRET);
  const auth = { preHandler: session };

  /** The signed-in user must be an owner; returns their id. */
  const owner = async (request: FastifyRequest): Promise<string> => {
    const me = sessionOf(request).sub;
    const user = await db.user.findUnique({ where: { id: me }, select: { telegramId: true } });
    if (!user || !ctx.users.isOwnerTelegram(user.telegramId)) throw new AppError('FORBIDDEN');
    return me;
  };

  // ── announcement: everyone reads, the owner writes ──
  app.get('/announcement', auth, async (): Promise<AnnouncementDto | null> => {
    const row = await db.announcement.findFirst({ orderBy: { createdAt: 'desc' } });
    return row ? { id: row.id, title: row.title, text: row.text, createdAt: row.createdAt.toISOString() } : null;
  });

  app.put('/owner/announcement', auth, async (request): Promise<AnnouncementDto> => {
    const me = await owner(request);
    const body = z.object({ title: z.string().trim().max(80).default(''), text: z.string().trim().min(1).max(1500) }).parse(request.body);
    // A new row every time: a new id makes the pop-up show again for everyone who closed the old one.
    const row = await db.$transaction(async (tx) => {
      await tx.announcement.deleteMany({});
      return tx.announcement.create({ data: { title: body.title, text: body.text, createdBy: me } });
    });
    return { id: row.id, title: row.title, text: row.text, createdAt: row.createdAt.toISOString() };
  });

  app.delete('/owner/announcement', auth, async (request) => {
    await owner(request);
    await db.announcement.deleteMany({});
    return { ok: true };
  });

  // ── gifts ──
  app.get('/owner/players', auth, async (request): Promise<OwnerPlayerDto[]> => {
    await owner(request);
    const { q } = z.object({ q: z.string().max(64).default('') }).parse(request.query);
    const query = q.trim().replace(/^@/, '');
    const where: Prisma.UserWhereInput = !query
      ? {}
      : /^\d{3,}$/.test(query)
        ? { telegramId: BigInt(query) }
        : {
            OR: [
              { username: { contains: query, mode: 'insensitive' } },
              { firstName: { contains: query, mode: 'insensitive' } },
              { lastName: { contains: query, mode: 'insensitive' } },
              { profile: { nickname: { contains: query, mode: 'insensitive' } } },
            ],
          };
    const users = await db.user.findMany({
      where: { ...where, profile: { isNot: null } },
      include: { profile: true, wallets: true },
      orderBy: { lastSeenAt: 'desc' },
      take: 30,
    });
    return users.map((u) => ({
      id: u.id,
      telegramId: u.telegramId.toString(),
      name: u.profile!.nickname || displayName(u),
      username: u.username,
      photoUrl: avatarUrl(u, u.profile!),
      credits: toNumber(u.wallets.find((w) => w.currency === 'CREDITS')?.balance ?? 0n),
      coins: toNumber(u.wallets.find((w) => w.currency === 'COINS')?.balance ?? 0n),
    }));
  });

  app.post('/owner/players/:userId/wallet', auth, async (request) => {
    const me = await owner(request);
    const { userId } = userParam.parse(request.params);
    const body = z
      .object({
        currency: z.enum(['CREDITS', 'COINS']),
        amount: z.number().int().refine((v) => v !== 0 && Math.abs(v) <= 1_000_000_000, 'amount'),
        requestId: z.string().min(8).max(64),
      })
      .parse(request.body);
    const user = await db.user.findUnique({ where: { id: userId }, select: { id: true } });
    if (!user) throw new AppError('NOT_FOUND');
    const tx = await db.$transaction((t) =>
      ctx.ledger.postIn(t, {
        userId,
        currency: body.currency,
        amount: BigInt(body.amount),
        type: 'ADMIN',
        source: `owner:${me}`,
        idempotencyKey: `owner:${body.requestId}`,
        meta: { reason: 'Подарок от администрации', owner: me },
      }),
    );
    return { balance: toNumber(tx.balanceAfter) };
  });

  app.get('/owner/players/:userId/items', auth, async (request) => {
    await owner(request);
    const { userId } = userParam.parse(request.params);
    const [items, owned] = await Promise.all([
      db.item.findMany({ where: { price: { gt: 0 }, isActive: true }, orderBy: { sortOrder: 'asc' } }),
      db.userItem.findMany({ where: { userId }, select: { itemId: true } }),
    ]);
    const have = new Set(owned.map((o) => o.itemId));
    return items.map((i) => ({ key: i.key, name: i.name, kind: i.kind, owned: have.has(i.id) }));
  });

  app.post('/owner/players/:userId/items', auth, async (request) => {
    await owner(request);
    const { userId } = userParam.parse(request.params);
    const { key, take } = z.object({ key: z.string().max(64), take: z.boolean().default(false) }).parse(request.body);
    const item = await db.item.findUnique({ where: { key } });
    if (!item) throw new AppError('NOT_FOUND');
    if (take) await db.userItem.deleteMany({ where: { userId, itemId: item.id } });
    else
      await db.userItem.upsert({
        where: { userId_itemId: { userId, itemId: item.id } },
        create: { userId, itemId: item.id, source: 'gift' },
        update: {},
      });
    return { ok: true };
  });

  // ── welcome gift for newcomers, and a one-off gift to everyone short of credits ──
  const welcomeBody = z.object({
    enabled: z.boolean(),
    credits: z.number().int().min(0).max(1_000_000_000),
    coins: z.number().int().min(0).max(1_000_000_000),
  });

  app.get('/owner/welcome', auth, async (request): Promise<WelcomeGiftDto> => {
    await owner(request);
    return ctx.welcome.get();
  });

  app.put('/owner/welcome', auth, async (request): Promise<WelcomeGiftDto> => {
    await owner(request);
    return ctx.welcome.set(welcomeBody.parse(request.body));
  });

  app.post('/owner/grant', auth, async (request) => {
    const me = await owner(request);
    const body = z
      .object({
        below: z.number().int().min(1).max(1_000_000_000),
        credits: z.number().int().min(0).max(1_000_000_000),
        coins: z.number().int().min(0).max(1_000_000_000),
        requestId: z.string().min(8).max(64),
      })
      .refine((b) => b.credits > 0 || b.coins > 0)
      .parse(request.body);
    return ctx.welcome.grantToPoor({ below: body.below, credits: body.credits, coins: body.coins, batch: body.requestId, by: me });
  });
}
