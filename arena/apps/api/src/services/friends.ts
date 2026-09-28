import type {
  FriendDto,
  FriendRequestsDto,
  PublicUserDto,
  RecentPlayerDto,
  Relation,
  SearchUserDto,
  SendRequestResult,
} from '@arena/shared';
import { roomDeepLink } from '@arena/shared';
import type { Config } from '../config.js';
import type { Db } from '../db.js';
import { AppError } from '../lib/errors.js';
import { inviteCode } from '../lib/ids.js';
import type { Realtime } from '../realtime/realtime.js';
import { progressAchievements } from './achievements.js';
import type { Ledger } from './ledger.js';
import type { Outbox } from './notifier.js';
import type { Presence } from './presence.js';
import { isBanned, publicUser } from './users.js';

/** Friends plus pending requests one player may have at a time. */
const LIMIT = 200;
/** One invite per friend per this interval: invites also go out as bot messages. */
const INVITE_COOLDOWN_MS = 30_000;

export class FriendService {
  private lastInvite = new Map<string, number>();

  constructor(
    private readonly deps: {
      config: Config;
      db: Db;
      ledger: Ledger;
      outbox: Outbox;
      presence: Presence;
      realtime: Realtime;
    },
  ) {}

  private get db(): Db {
    return this.deps.db;
  }

  private appLink(startapp?: string): string {
    const { BOT_USERNAME, MINI_APP_SHORT_NAME } = this.deps.config;
    const base = MINI_APP_SHORT_NAME ? `https://t.me/${BOT_USERNAME}/${MINI_APP_SHORT_NAME}` : `https://t.me/${BOT_USERNAME}`;
    return startapp ? `${base}?startapp=${startapp}` : base;
  }

  async list(me: string): Promise<FriendDto[]> {
    const rows = await this.db.friend.findMany({
      where: { userId: me },
      include: { friend: { include: { profile: true } } },
      take: LIMIT,
    });
    const presence = await this.deps.presence.lookup(rows.map((r) => r.friendId));
    const order = { in_game: 0, online: 1, offline: 2 } as const;
    return rows
      .filter((r) => r.friend.profile)
      .map((r) => ({ ...publicUser(r.friend, r.friend.profile!), presence: presence[r.friendId] ?? 'offline' }))
      .sort((a, b) => order[a.presence] - order[b.presence] || a.name.localeCompare(b.name, 'ru'));
  }

  async requests(me: string): Promise<FriendRequestsDto> {
    const include = { from: { include: { profile: true } }, to: { include: { profile: true } } } as const;
    const [incoming, outgoing] = await Promise.all([
      this.db.friendRequest.findMany({ where: { toId: me, status: 'PENDING' }, include, orderBy: { createdAt: 'desc' } }),
      this.db.friendRequest.findMany({ where: { fromId: me, status: 'PENDING' }, include, orderBy: { createdAt: 'desc' } }),
    ]);
    return {
      incoming: incoming.filter((r) => r.from.profile).map((r) => ({ id: r.id, user: publicUser(r.from, r.from.profile!), createdAt: r.createdAt.toISOString() })),
      outgoing: outgoing.filter((r) => r.to.profile).map((r) => ({ id: r.id, user: publicUser(r.to, r.to.profile!), createdAt: r.createdAt.toISOString() })),
    };
  }

  async relations(me: string, ids: string[]): Promise<Record<string, Relation>> {
    const [friends, requests] = await Promise.all([
      this.db.friend.findMany({ where: { userId: me, friendId: { in: ids } }, select: { friendId: true } }),
      this.db.friendRequest.findMany({
        where: { status: 'PENDING', OR: [{ fromId: me, toId: { in: ids } }, { toId: me, fromId: { in: ids } }] },
        select: { fromId: true, toId: true },
      }),
    ]);
    const result: Record<string, Relation> = {};
    for (const id of ids) result[id] = id === me ? 'self' : 'none';
    for (const r of requests) {
      if (r.fromId === me) result[r.toId] = 'outgoing';
      else result[r.fromId] = 'incoming';
    }
    for (const f of friends) result[f.friendId] = 'friend';
    return result;
  }

  async send(me: string, targetId: string): Promise<SendRequestResult> {
    if (me === targetId) throw new AppError('VALIDATION_FAILED');
    const target = await this.db.user.findUnique({ where: { id: targetId }, include: { profile: true } });
    if (!target?.profile || isBanned(target)) throw new AppError('NOT_FOUND');

    if (await this.db.friend.findUnique({ where: { userId_friendId: { userId: me, friendId: targetId } } })) {
      return { status: 'already_friends' };
    }
    // They already asked me: asking back means yes.
    const reverse = await this.db.friendRequest.findUnique({ where: { fromId_toId: { fromId: targetId, toId: me } } });
    if (reverse?.status === 'PENDING') {
      await this.accept(me, reverse.id);
      return { status: 'friends' };
    }
    const existing = await this.db.friendRequest.findUnique({ where: { fromId_toId: { fromId: me, toId: targetId } } });
    if (existing?.status === 'PENDING') return { status: 'already_sent' };

    const [friends, pending] = await Promise.all([
      this.db.friend.count({ where: { userId: me } }),
      this.db.friendRequest.count({ where: { fromId: me, status: 'PENDING' } }),
    ]);
    if (friends + pending >= LIMIT) throw new AppError('FRIEND_LIMIT');

    await this.db.friendRequest.upsert({
      where: { fromId_toId: { fromId: me, toId: targetId } },
      create: { fromId: me, toId: targetId },
      update: { status: 'PENDING', createdAt: new Date(), respondedAt: null },
    });

    const from = await this.publicOf(me);
    if (this.deps.realtime.hub.isOnline(targetId)) {
      this.deps.realtime.hub.send(targetId, { type: 'FRIEND_REQUEST', from });
    } else {
      await this.deps.outbox.enqueue(targetId, 'friend_request', {
        text: `👋 <b>${escapeHtml(from.name)}</b> хочет добавить вас в друзья в Маруська Арене.`,
        button: { text: 'Открыть', url: this.appLink('friends') },
      });
    }
    return { status: 'sent' };
  }

  async accept(me: string, requestId: string): Promise<void> {
    const request = await this.db.friendRequest.findUnique({ where: { id: requestId } });
    if (!request || request.toId !== me || request.status !== 'PENDING') throw new AppError('NOT_FOUND');
    await this.db.$transaction(async (tx) => {
      const claimed = await tx.friendRequest.updateMany({
        where: { id: requestId, status: 'PENDING' },
        data: { status: 'ACCEPTED', respondedAt: new Date() },
      });
      if (claimed.count === 0) return;
      await tx.friend.createMany({
        data: [
          { userId: request.fromId, friendId: request.toId },
          { userId: request.toId, friendId: request.fromId },
        ],
        skipDuplicates: true,
      });
      // The other direction may be pending too; it is settled by this friendship.
      await tx.friendRequest.updateMany({
        where: { fromId: request.toId, toId: request.fromId, status: 'PENDING' },
        data: { status: 'ACCEPTED', respondedAt: new Date() },
      });
      for (const userId of [request.fromId, request.toId]) {
        const count = await tx.friend.count({ where: { userId } });
        await progressAchievements(tx, this.deps.ledger, userId, 'friends', { social_5: count });
      }
    });
    this.deps.realtime.hub.send(request.fromId, { type: 'FRIEND_ACCEPTED', friend: await this.publicOf(me) });
  }

  async decline(me: string, requestId: string): Promise<void> {
    const done = await this.db.friendRequest.updateMany({
      where: { id: requestId, toId: me, status: 'PENDING' },
      data: { status: 'DECLINED', respondedAt: new Date() },
    });
    if (!done.count) throw new AppError('NOT_FOUND');
  }

  async cancel(me: string, requestId: string): Promise<void> {
    const done = await this.db.friendRequest.updateMany({
      where: { id: requestId, fromId: me, status: 'PENDING' },
      data: { status: 'CANCELLED', respondedAt: new Date() },
    });
    if (!done.count) throw new AppError('NOT_FOUND');
  }

  async remove(me: string, friendId: string): Promise<void> {
    await this.db.friend.deleteMany({
      where: { OR: [{ userId: me, friendId }, { userId: friendId, friendId: me }] },
    });
  }

  /** People from my last games — the natural place to find new friends. */
  async recent(me: string): Promise<RecentPlayerDto[]> {
    const games = await this.db.gamePlayer.findMany({
      where: { userId: me, game: { status: 'FINISHED' } },
      orderBy: { game: { startedAt: 'desc' } },
      take: 30,
      select: { gameId: true, game: { select: { startedAt: true } } },
    });
    if (!games.length) return [];
    const others = await this.db.gamePlayer.findMany({
      where: { gameId: { in: games.map((g) => g.gameId) }, userId: { not: me } },
      include: { user: { include: { profile: true } }, game: { select: { startedAt: true } } },
    });
    const byUser = new Map<string, { user: (typeof others)[number]['user']; last: Date; games: number }>();
    for (const o of others) {
      const entry = byUser.get(o.userId);
      if (!entry) byUser.set(o.userId, { user: o.user, last: o.game.startedAt, games: 1 });
      else {
        entry.games++;
        if (o.game.startedAt > entry.last) entry.last = o.game.startedAt;
      }
    }
    const relations = await this.relations(me, [...byUser.keys()]);
    return [...byUser.values()]
      .filter((e) => e.user.profile && !isBanned(e.user))
      .sort((a, b) => b.last.getTime() - a.last.getTime())
      .slice(0, 30)
      .map((e) => ({
        ...publicUser(e.user, e.user.profile!),
        relation: relations[e.user.id] ?? 'none',
        lastPlayedAt: e.last.toISOString(),
        games: e.games,
      }));
  }

  /** By Telegram @username prefix; nothing else about a player is searchable. */
  async search(me: string, query: string): Promise<SearchUserDto[]> {
    const q = query.trim().replace(/^@/, '');
    if (q.length < 3) return [];
    const users = await this.db.user.findMany({
      where: { username: { startsWith: q, mode: 'insensitive' }, bannedAt: null, id: { not: me } },
      include: { profile: true },
      take: 20,
    });
    const relations = await this.relations(me, users.map((u) => u.id));
    return users.filter((u) => u.profile).map((u) => ({ ...publicUser(u, u.profile!), relation: relations[u.id] ?? 'none' }));
  }

  /** Call a friend to my waiting room: instantly in the app, or with a bot message if they are away. */
  async invite(me: string, friendId: string): Promise<void> {
    const friendship = await this.db.friend.findUnique({ where: { userId_friendId: { userId: me, friendId } } });
    if (!friendship) throw new AppError('NOT_FRIENDS');
    const room = this.deps.realtime.rooms.roomOf(me);
    if (!room || room.status !== 'waiting') throw new AppError('NOT_IN_ROOM');
    if (room.seats.length >= room.settings.players) throw new AppError('ROOM_FULL');

    const key = `${me}:${friendId}`;
    const now = Date.now();
    if (now - (this.lastInvite.get(key) ?? 0) < INVITE_COOLDOWN_MS) throw new AppError('RATE_LIMITED');
    this.lastInvite.set(key, now);

    const code = inviteCode(room.id, this.deps.config.SESSION_SECRET);
    const from = await this.publicOf(me);
    const hub = this.deps.realtime.hub;
    if (hub.isOnline(friendId)) {
      hub.send(friendId, { type: 'ROOM_INVITE', from, room: this.deps.realtime.rooms.dto(room), invite: code });
      return;
    }
    const link = roomDeepLink(this.deps.config.BOT_USERNAME, this.deps.config.MINI_APP_SHORT_NAME || null, room.id, code);
    await this.deps.outbox.enqueue(friendId, 'room_invite', {
      text: `🃏 <b>${escapeHtml(from.name)}</b> зовёт вас сыграть в дурака. Ставка ${room.settings.stake}.`,
      button: { text: '🎮 Играть', url: link },
    });
  }

  private async publicOf(userId: string): Promise<PublicUserDto> {
    const user = await this.db.user.findUniqueOrThrow({ where: { id: userId }, include: { profile: true } });
    return publicUser(user, user.profile!);
  }
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
