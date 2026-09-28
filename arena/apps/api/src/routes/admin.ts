import { DAILY_CREDITS, FEATURE_PRICES, formatStake, ratingBadge, STAKE_OPTIONS } from '@arena/shared';
import type { FastifyInstance, FastifyRequest } from 'fastify';
import { z } from 'zod';
import type { Context } from '../context.js';
import type { Prisma } from '../generated/prisma/client.js';
import { AppError } from '../lib/errors.js';
import { toNumber } from '../lib/money.js';
import { avatarUrl, displayName } from '../services/users.js';

const tg = z.object({ telegramId: z.coerce.bigint() });
const DAY = 86_400_000;
const BROADCAST_MAX = 50_000;

/**
 * Everything the bot's admin panel («🃏 Арена») can see and do. Mounted under the internal API:
 * the bot calls it with the shared secret and checks on its side that the caller is an owner.
 */
export async function adminRoutes(app: FastifyInstance, ctx: Context, check: (r: FastifyRequest) => Promise<void>): Promise<void> {
  const { db } = ctx;
  const opts = { preHandler: check };

  const userByTelegram = async (telegramId: bigint) => {
    const user = await db.user.findUnique({ where: { telegramId }, include: { profile: true } });
    if (!user?.profile) throw new AppError('NOT_FOUND');
    return user as typeof user & { profile: NonNullable<typeof user.profile> };
  };

  // ── overview ──
  app.get('/internal/admin/overview', opts, async () => {
    const now = Date.now();
    const today = new Date(now - (now % DAY));
    const week = new Date(now - 7 * DAY);
    const [players, newToday, active7, gamesToday, games7, stakes, bans, reports7, outbox] = await Promise.all([
      db.profile.count(),
      db.user.count({ where: { createdAt: { gte: today } } }),
      db.user.count({ where: { lastSeenAt: { gte: week } } }),
      db.game.count({ where: { startedAt: { gte: today } } }),
      db.game.count({ where: { startedAt: { gte: week } } }),
      db.game.aggregate({ where: { startedAt: { gte: today }, status: 'FINISHED' }, _sum: { stake: true } }),
      db.user.count({ where: { bannedAt: { not: null }, OR: [{ bannedUntil: null }, { bannedUntil: { gt: new Date() } }] } }),
      db.playerReport.count({ where: { createdAt: { gte: week } } }),
      db.notification.count({ where: { sentAt: null, attempts: { lt: 5 } } }),
    ]);
    // Rake = what the table keeps: sum of all nets of finished games today is minus the rake.
    const rake = await db.gamePlayer.aggregate({ where: { game: { startedAt: { gte: today }, status: 'FINISHED' } }, _sum: { net: true } });
    const top = await db.gamePlayer.groupBy({
      by: ['userId'],
      where: { game: { startedAt: { gte: today }, status: 'FINISHED' } },
      _sum: { net: true },
      orderBy: { _sum: { net: 'desc' } },
      take: 5,
    });
    const names = await db.user.findMany({ where: { id: { in: top.map((t) => t.userId) } }, include: { profile: true } });
    const rooms = ctx.realtime.rooms.list();
    return {
      online: ctx.realtime.hub.onlineUsers().length,
      gamesRunning: ctx.realtime.games.count(),
      roomsWaiting: rooms.filter((r) => r.status === 'waiting').length,
      players,
      newToday,
      active7,
      gamesToday,
      games7,
      stakedToday: toNumber(stakes._sum.stake ?? 0n),
      rakeToday: -toNumber(rake._sum.net ?? 0n),
      bans,
      reports7,
      outbox,
      topWinners: top.map((t) => {
        const u = names.find((n) => n.id === t.userId);
        return { telegramId: u?.telegramId.toString() ?? '', name: u ? u.profile?.nickname || displayName(u) : '?', net: toNumber(t._sum.net ?? 0n) };
      }),
    };
  });

  // ── players ──
  app.get('/internal/admin/players', opts, async (request) => {
    const { q, limit } = z.object({ q: z.string().max(64).default(''), limit: z.coerce.number().int().min(1).max(100).default(30) }).parse(request.query);
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
    const users = await db.user.findMany({ where: { ...where, profile: { isNot: null } }, include: { profile: true, wallets: true }, orderBy: { lastSeenAt: 'desc' }, take: limit });
    return users.map((u) => ({
      telegramId: u.telegramId.toString(),
      name: u.profile!.nickname || displayName(u),
      username: u.username,
      photoUrl: avatarUrl(u, u.profile!),
      rating: u.profile!.rating,
      credits: toNumber(u.wallets.find((w) => w.currency === 'CREDITS')?.balance ?? 0n),
      games: u.profile!.gamesPlayed,
      banned: ctx.moderation.isBanned(u.id),
      lastSeenAt: u.lastSeenAt.toISOString(),
    }));
  });

  app.get('/internal/admin/players/:telegramId', opts, async (request) => {
    const user = await userByTelegram(tg.parse(request.params).telegramId);
    const p = user.profile;
    const [wallets, items, games, transactions, reports, notes] = await Promise.all([
      db.wallet.findMany({ where: { userId: user.id } }),
      db.userItem.findMany({ where: { userId: user.id }, include: { item: true } }),
      db.gamePlayer.findMany({ where: { userId: user.id }, orderBy: { game: { startedAt: 'desc' } }, take: 15, include: { game: { include: { players: true } } } }),
      db.transaction.findMany({ where: { userId: user.id }, orderBy: { createdAt: 'desc' }, take: 30 }),
      db.playerReport.groupBy({ by: ['reason'], where: { targetId: user.id }, _count: { _all: true } }),
      db.playerNote.count({ where: { targetId: user.id } }),
    ]);
    const badge = ratingBadge(p.rating);
    const room = ctx.realtime.rooms.roomOf(user.id);
    const game = ctx.realtime.games.forUser(user.id);
    return {
      telegramId: user.telegramId.toString(),
      id: user.id,
      name: p.nickname || displayName(user),
      telegramName: displayName(user),
      nickname: p.nickname,
      username: user.username,
      photoUrl: avatarUrl(user, p),
      customAvatar: p.avatarVersion !== null,
      createdAt: user.createdAt.toISOString(),
      lastSeenAt: user.lastSeenAt.toISOString(),
      online: ctx.realtime.hub.isOnline(user.id),
      at: game ? { kind: 'game', id: game.id } : room ? { kind: 'room', id: room.id } : null,
      ban: user.bannedAt ? { at: user.bannedAt.toISOString(), until: user.bannedUntil?.toISOString() ?? null, reason: user.banReason, active: ctx.moderation.isBanned(user.id) } : null,
      premiumUntil: p.premiumUntil?.toISOString() ?? null,
      wallet: Object.fromEntries(wallets.map((w) => [w.currency, toNumber(w.balance)])),
      stats: {
        rating: p.rating,
        league: badge.league.name,
        level: badge.level,
        games: p.gamesPlayed,
        wins: p.gamesWon,
        losses: p.gamesLost,
        draws: p.gamesDraw,
        winnings: toNumber(p.totalWinnings),
        streak: p.winStreak,
        bestStreak: p.bestStreak,
        caughtCheating: p.caughtCheating,
      },
      items: items.map((i) => ({ key: i.item.key, name: i.item.name, kind: i.item.kind, equipped: i.equipped, source: i.source })),
      games: games.map((g) => ({
        id: g.gameId,
        status: g.game.status,
        stake: toNumber(g.game.stake),
        players: g.game.players.length,
        net: g.net === null ? null : toNumber(g.net),
        outcome: g.outcome,
        startedAt: g.game.startedAt.toISOString(),
      })),
      transactions: transactions.map((t) => ({
        at: t.createdAt.toISOString(),
        type: t.type,
        currency: t.currency,
        amount: toNumber(t.amount),
        after: toNumber(t.balanceAfter),
        source: t.source,
      })),
      reports: Object.fromEntries(reports.map((r) => [r.reason, r._count._all])),
      labelledBy: notes,
    };
  });

  /** Credit or debit a wallet through the ledger (never below zero). */
  app.post('/internal/admin/players/:telegramId/wallet', opts, async (request) => {
    const user = await userByTelegram(tg.parse(request.params).telegramId);
    const body = z
      .object({
        currency: z.enum(['CREDITS', 'COINS', 'DIAMONDS']),
        amount: z.number().int().refine((v) => v !== 0 && Math.abs(v) <= 1_000_000_000, 'amount'),
        reason: z.string().min(2).max(200),
        requestId: z.string().min(8).max(64),
        admin: z.string().max(64).optional(),
      })
      .parse(request.body);
    const tx = await db.$transaction((t) =>
      ctx.ledger.postIn(t, {
        userId: user.id,
        currency: body.currency,
        amount: BigInt(body.amount),
        type: 'ADMIN',
        source: `admin:${body.admin ?? 'panel'}`.slice(0, 128),
        idempotencyKey: `admin:${body.requestId}`,
        meta: { reason: body.reason, admin: body.admin ?? null },
      }),
    );
    return { balance: toNumber(tx.balanceAfter) };
  });

  app.post('/internal/admin/players/:telegramId/premium', opts, async (request) => {
    const user = await userByTelegram(tg.parse(request.params).telegramId);
    const { days } = z.object({ days: z.number().int().min(0).max(3650) }).parse(request.body);
    const base = user.profile.premiumUntil && user.profile.premiumUntil.getTime() > Date.now() ? user.profile.premiumUntil.getTime() : Date.now();
    const until = days === 0 ? null : new Date(base + days * DAY);
    await db.profile.update({ where: { userId: user.id }, data: { premiumUntil: until } });
    return { premiumUntil: until?.toISOString() ?? null };
  });

  /** Moderation of names and pictures: back to the Telegram ones. */
  app.post('/internal/admin/players/:telegramId/reset', opts, async (request) => {
    const user = await userByTelegram(tg.parse(request.params).telegramId);
    const { what } = z.object({ what: z.enum(['nickname', 'avatar']) }).parse(request.body);
    if (what === 'nickname') await db.profile.update({ where: { userId: user.id }, data: { nickname: null } });
    else
      await db.$transaction([
        db.userAvatar.deleteMany({ where: { userId: user.id } }),
        db.profile.update({ where: { userId: user.id }, data: { avatarVersion: null } }),
      ]);
    return { ok: true };
  });

  app.post('/internal/admin/players/:telegramId/items', opts, async (request) => {
    const user = await userByTelegram(tg.parse(request.params).telegramId);
    const { key, take } = z.object({ key: z.string().max(64), take: z.boolean().default(false) }).parse(request.body);
    const item = await db.item.findUnique({ where: { key } });
    if (!item) throw new AppError('NOT_FOUND');
    if (take) await db.userItem.deleteMany({ where: { userId: user.id, itemId: item.id } });
    else await db.userItem.upsert({ where: { userId_itemId: { userId: user.id, itemId: item.id } }, create: { userId: user.id, itemId: item.id, source: 'admin' }, update: {} });
    return { ok: true };
  });

  // ── live tables ──
  app.get('/internal/admin/live', opts, async () => {
    const rooms = ctx.realtime.rooms.list();
    const games = ctx.realtime.games.all().map((g) => g.summary()).filter((g) => !g.finished);
    return {
      rooms: rooms
        .filter((r) => r.status === 'waiting')
        .map((r) => ({
          id: r.id,
          stake: r.settings.stake,
          players: r.settings.players,
          isPrivate: r.isPrivate,
          tournament: r.tournament?.title ?? null,
          createdAt: new Date(r.createdAt).toISOString(),
          seats: r.seats.map((s) => ({ name: s.name, ready: s.ready, connected: s.connected })),
          rules: `${r.settings.deckSize} карт · ${r.settings.variant === 'perevodnoy' ? 'переводной' : 'подкидной'} · ${formatStake(r.settings.stake)}`,
        })),
      games: games.map((g) => ({ ...g, startedAt: new Date(g.startedAt).toISOString() })),
    };
  });

  app.post('/internal/admin/games/:id/abort', opts, async (request) => {
    const { id } = z.object({ id: z.uuid() }).parse(request.params);
    if (await ctx.realtime.games.abort(id)) return { ok: true };
    // Not in this process: a stuck row in the database; refund it directly.
    const game = await db.game.findUnique({ where: { id }, select: { status: true } });
    if (game?.status !== 'PLAYING') throw new AppError('NOT_FOUND');
    await ctx.realtime.settlement.abort(id);
    return { ok: true };
  });

  app.post('/internal/admin/rooms/:id/close', opts, async (request) => {
    const { id } = z.object({ id: z.string().regex(/^[A-Z0-9]{8}$/) }).parse(request.params);
    if (!(await ctx.realtime.rooms.adminClose(id))) throw new AppError('NOT_FOUND');
    return { ok: true };
  });

  // ── tournaments ──
  app.get('/internal/admin/tournaments', opts, async () => {
    const rows = await db.tournament.findMany({ orderBy: { startsAt: 'desc' }, take: 50, include: { _count: { select: { players: true } } } });
    return rows.map((t) => ({
      id: t.id,
      title: t.title,
      status: t.status,
      entryFee: toNumber(t.entryFee),
      prizePool: toNumber(t.prizePool),
      currency: t.currency,
      maxPlayers: t.maxPlayers,
      registered: t._count.players,
      startsAt: t.startsAt.toISOString(),
      finishedAt: t.finishedAt?.toISOString() ?? null,
    }));
  });

  app.post('/internal/admin/tournaments/:id/cancel', opts, async (request) => {
    const { id } = z.object({ id: z.uuid() }).parse(request.params);
    if (!(await ctx.tournaments.adminCancel(id))) throw new AppError('NOT_FOUND');
    return { ok: true };
  });

  // ── seasons ──
  app.get('/internal/admin/seasons', opts, async () => {
    const rows = await db.season.findMany({ orderBy: { startsAt: 'desc' }, take: 20, include: { _count: { select: { ratings: true } } } });
    return rows.map((s) => ({ id: s.id, title: s.title, startsAt: s.startsAt.toISOString(), endsAt: s.endsAt.toISOString(), players: s._count.ratings, rewarded: s.rewarded }));
  });

  app.post('/internal/admin/seasons', opts, async (request) => {
    const body = z.object({ title: z.string().min(2).max(128), startsAt: z.iso.datetime(), endsAt: z.iso.datetime() }).parse(request.body);
    const startsAt = new Date(body.startsAt);
    const endsAt = new Date(body.endsAt);
    if (endsAt <= startsAt) throw new AppError('VALIDATION_FAILED');
    const overlap = await db.season.count({ where: { startsAt: { lt: endsAt }, endsAt: { gt: startsAt } } });
    if (overlap) throw new AppError('VALIDATION_FAILED');
    const season = await db.season.create({ data: { title: body.title, startsAt, endsAt } });
    return { id: season.id };
  });

  app.post('/internal/admin/seasons/:id/end', opts, async (request) => {
    const { id } = z.object({ id: z.uuid() }).parse(request.params);
    const updated = await db.season.updateMany({ where: { id, endsAt: { gt: new Date() } }, data: { endsAt: new Date() } });
    if (!updated.count) throw new AppError('NOT_FOUND');
    return { ok: true };
  });

  // ── shop ──
  app.get('/internal/admin/items', opts, async () => {
    const rows = await db.item.findMany({ orderBy: { sortOrder: 'asc' }, include: { _count: { select: { owners: true } } } });
    return rows.map((i) => ({
      key: i.key,
      kind: i.kind,
      name: i.name,
      rarity: i.rarity,
      price: toNumber(i.price),
      currency: i.currency,
      isActive: i.isActive,
      owners: i._count.owners,
      overridden: i.adminOverride,
    }));
  });

  app.post('/internal/admin/items/:key', opts, async (request) => {
    const { key } = z.object({ key: z.string().max(64) }).parse(request.params);
    const body = z
      .object({
        name: z.string().min(2).max(128).optional(),
        price: z.number().int().min(0).max(1_000_000_000).optional(),
        currency: z.enum(['CREDITS', 'COINS']).optional(),
        isActive: z.boolean().optional(),
      })
      .parse(request.body);
    const item = await db.item.findUnique({ where: { key } });
    if (!item) throw new AppError('NOT_FOUND');
    await db.item.update({
      where: { key },
      data: { ...body, ...(body.price !== undefined ? { price: BigInt(body.price) } : {}), adminOverride: true },
    });
    return { ok: true };
  });

  // ── broadcast to arena players (private messages from the bot) ──
  app.post('/internal/admin/broadcast', opts, async (request) => {
    const body = z
      .object({
        text: z.string().min(1).max(3500),
        audience: z.enum(['all', 'active7', 'active30']).default('active30'),
        button: z.boolean().default(true),
        dryRun: z.boolean().default(false),
      })
      .parse(request.body);
    const since = body.audience === 'all' ? null : new Date(Date.now() - (body.audience === 'active7' ? 7 : 30) * DAY);
    const users = await db.user.findMany({
      where: { profile: { isNot: null }, bannedAt: null, ...(since ? { lastSeenAt: { gte: since } } : {}) },
      select: { id: true },
      take: BROADCAST_MAX,
    });
    if (body.dryRun) return { recipients: users.length };
    const link = ctx.config.MINI_APP_SHORT_NAME ? `https://t.me/${ctx.config.BOT_USERNAME}/${ctx.config.MINI_APP_SHORT_NAME}` : null;
    const payload = { text: body.text, ...(body.button && link ? { button: { text: '🃏 Играть', url: link } } : {}) };
    for (let i = 0; i < users.length; i += 1000) {
      await db.notification.createMany({ data: users.slice(i, i + 1000).map((u) => ({ userId: u.id, kind: 'broadcast', payload })) });
    }
    ctx.outbox.hurry();
    return { recipients: users.length };
  });

  // ── rules and economy, read-only (changed through Railway variables) ──
  app.get('/internal/admin/settings', opts, async () => ({
    signupBonus: ctx.config.SIGNUP_BONUS_CREDITS,
    rakePercent: ctx.config.RAKE_PERCENT,
    dailyCredits: DAILY_CREDITS,
    featurePrices: FEATURE_PRICES,
    stakes: STAKE_OPTIONS,
    readySeconds: ctx.config.MATCH_READY_SECONDS,
    botUsername: ctx.config.BOT_USERNAME,
    miniApp: ctx.config.MINI_APP_SHORT_NAME,
  }));
}
