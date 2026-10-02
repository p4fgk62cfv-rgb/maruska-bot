import type {
  FavoriteDto,
  FriendDto,
  Presence as PresenceState,
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
/** «Избранные» per player. */
const FAVORITES_LIMIT = 100;

export class FriendService {
  private lastInvite = new Map<string, number>();
  /** Last presence told to friends, so a reconnect blink is not announced twice. */
  private told = new Map<string, PresenceState>();
  /** «Сообщить, когда освободится»: player in a game → who wants to know. One-shot, kept in memory. */
  private watchers = new Map<string, Set<string>>();

  constructor(
    private readonly deps: {
      config: Config;
      db: Db;
      ledger: Ledger;
      outbox: Outbox;
      presence: Presence;
      realtime: Realtime;
    },
  ) {
    deps.realtime.onPresence((ids) => {
      void this.presenceChanged(ids).catch(() => undefined);
    });
  }

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
    const ids = rows.map((r) => r.friendId);
    const [presence, favorites] = await Promise.all([this.deps.presence.lookup(ids), this.favoriteSet(me, ids)]);
    return rows
      .filter((r) => r.friend.profile)
      .map((r) => ({
        ...publicUser(r.friend, r.friend.profile!),
        presence: presence[r.friendId] ?? 'offline',
        lastSeenAt: r.friend.lastSeenAt.toISOString(),
        favorite: favorites.has(r.friendId),
        watching: this.watchers.get(r.friendId)?.has(me) ?? false,
      }))
      .sort(byPresence);
  }

  // ── «Избранные игроки» ─────────────────────────────────────

  private async favoriteSet(me: string, ids: string[]): Promise<Set<string>> {
    if (!ids.length) return new Set();
    const rows = await this.db.favorite.findMany({ where: { ownerId: me, targetId: { in: ids } }, select: { targetId: true } });
    return new Set(rows.map((r) => r.targetId));
  }

  async isFavorite(me: string, targetId: string): Promise<boolean> {
    return (await this.db.favorite.count({ where: { ownerId: me, targetId } })) > 0;
  }

  async favorites(me: string): Promise<FavoriteDto[]> {
    const rows = await this.db.favorite.findMany({
      where: { ownerId: me },
      include: { target: { include: { profile: true } } },
      orderBy: { createdAt: 'desc' },
      take: FAVORITES_LIMIT,
    });
    const live = rows.filter((r) => r.target.profile && !isBanned(r.target));
    const ids = live.map((r) => r.targetId);
    const [presence, relations] = await Promise.all([this.deps.presence.lookup(ids), this.relations(me, ids)]);
    return live
      .map((r) => ({
        ...publicUser(r.target, r.target.profile!),
        presence: presence[r.targetId] ?? 'offline',
        lastSeenAt: r.target.lastSeenAt.toISOString(),
        favorite: true,
        watching: this.watchers.get(r.targetId)?.has(me) ?? false,
        relation: relations[r.targetId] ?? 'none',
      }))
      .sort(byPresence);
  }

  async setFavorite(me: string, targetId: string, on: boolean): Promise<{ favorite: boolean }> {
    if (me === targetId) throw new AppError('VALIDATION_FAILED');
    if (!on) {
      await this.db.favorite.deleteMany({ where: { ownerId: me, targetId } });
      return { favorite: false };
    }
    const target = await this.db.user.findUnique({ where: { id: targetId }, select: { id: true, bannedAt: true } });
    if (!target || target.bannedAt) throw new AppError('NOT_FOUND');
    if ((await this.db.favorite.count({ where: { ownerId: me } })) >= FAVORITES_LIMIT) throw new AppError('FRIEND_LIMIT');
    await this.db.favorite.upsert({ where: { ownerId_targetId: { ownerId: me, targetId } }, create: { ownerId: me, targetId }, update: {} });
    return { favorite: true };
  }

  // ── presence: «в сети», «в игре», «освободился» ────────────

  /** «Сообщить, когда освободится» for a friend or a favourite who is playing right now. */
  async watch(me: string, targetId: string, on: boolean): Promise<{ watching: boolean; presence: PresenceState }> {
    const [friend, favorite] = await Promise.all([
      this.db.friend.count({ where: { userId: me, friendId: targetId } }),
      this.db.favorite.count({ where: { ownerId: me, targetId } }),
    ]);
    if (!friend && !favorite) throw new AppError('NOT_FRIENDS');
    const presence = (await this.deps.presence.lookup([targetId]))[targetId] ?? 'offline';
    const set = this.watchers.get(targetId) ?? new Set<string>();
    if (on && presence === 'in_game') {
      set.add(me);
      this.watchers.set(targetId, set);
    } else {
      set.delete(me);
      if (!set.size) this.watchers.delete(targetId);
    }
    return { watching: set.has(me), presence };
  }

  /** Who should hear about this player's presence: their friends and those who keep them in favourites. */
  private async audience(userId: string): Promise<string[]> {
    const [friends, fans] = await Promise.all([
      this.db.friend.findMany({ where: { userId }, select: { friendId: true } }),
      this.db.favorite.findMany({ where: { targetId: userId }, select: { ownerId: true } }),
    ]);
    return [...new Set([...friends.map((f) => f.friendId), ...fans.map((f) => f.ownerId)])];
  }

  async presenceChanged(ids: string[]): Promise<void> {
    const hub = this.deps.realtime.hub;
    const now = await this.deps.presence.lookup(ids);
    for (const id of ids) {
      const presence = now[id] ?? 'offline';
      const before = this.told.get(id);
      if (before === presence) continue;
      if (presence === 'offline') this.told.delete(id);
      else this.told.set(id, presence);

      const audience = (await this.audience(id)).filter((u) => hub.isOnline(u));
      for (const u of audience) hub.send(u, { type: 'FRIEND_PRESENCE', userId: id, presence });

      const waiting = this.watchers.get(id);
      if (before === 'in_game' && presence !== 'in_game' && waiting?.size) {
        this.watchers.delete(id);
        const friend = await this.publicOf(id);
        for (const watcher of waiting) {
          if (hub.isOnline(watcher)) hub.send(watcher, { type: 'FRIEND_FREE', friend, presence });
          else {
            await this.deps.outbox.enqueue(watcher, 'friend_free', {
              text: `🟢 <b>${escapeHtml(friend.name)}</b> закончил(а) партию — самое время позвать в игру.`,
              button: { text: 'Открыть', url: this.appLink('friends') },
            });
          }
        }
      }
    }
  }

  /** Second-degree connections, excluding myself and existing friends. Shows only mutual-friend names. */
  async friendsOfFriends(me: string): Promise<(PublicUserDto & { mutualFriends: string[]; relation: Relation })[]> {
    const direct = await this.db.friend.findMany({ where: { userId: me }, select: { friendId: true } });
    if (!direct.length) return [];
    const directIds = direct.map((r) => r.friendId);
    const second = await this.db.friend.findMany({
      where: { userId: { in: directIds }, friendId: { notIn: [me, ...directIds] } },
      include: { friend: { include: { profile: true } }, user: { include: { profile: true } } },
    });
    const byUser = new Map<string, { user: (typeof second)[number]['friend']; mutual: Map<string, string> }>();
    for (const edge of second) {
      if (!edge.friend.profile || isBanned(edge.friend)) continue;
      const entry = byUser.get(edge.friendId) ?? { user: edge.friend, mutual: new Map<string, string>() };
      if (edge.user.profile && !isBanned(edge.user)) entry.mutual.set(edge.userId, publicUser(edge.user, edge.user.profile).name);
      byUser.set(edge.friendId, entry);
    }
    return [...byUser.values()]
      .filter((entry) => entry.mutual.size > 0)
      .sort((a, b) => b.mutual.size - a.mutual.size || publicUser(a.user, a.user.profile!).name.localeCompare(publicUser(b.user, b.user.profile!).name, 'ru'))
      .slice(0, 100)
      .map((entry) => ({
        ...publicUser(entry.user, entry.user.profile!),
        mutualFriends: [...entry.mutual.values()],
        relation: 'none' as const,
      }));
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
    if (!target?.profile || isBanned(target) || target.isBot) throw new AppError('NOT_FOUND');

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
      .filter((e) => e.user.profile && !isBanned(e.user) && !e.user.isBot)
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
      where: { username: { startsWith: q, mode: 'insensitive' }, isBot: false, bannedAt: null, id: { not: me } },
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
    // The button opens the arena by its own address (a web_app button in the private chat with the
    // bot), so the invite works whatever the Mini App in BotFather points to.
    const base = publicUrl(this.deps.config);
    const startapp = `game_${room.id}_${code}`;
    await this.deps.outbox.enqueue(friendId, 'room_invite', {
      text: `🃏 <b>${escapeHtml(from.name)}</b> зовёт вас сыграть в дурака. Ставка ${room.settings.stake}.`,
      button: base
        ? { text: '🎮 Играть', webApp: `${base}/?start=${startapp}` }
        : { text: '🎮 Играть', url: roomDeepLink(this.deps.config.BOT_USERNAME, this.deps.config.MINI_APP_SHORT_NAME || null, room.id, code) },
    });
  }

  private async publicOf(userId: string): Promise<PublicUserDto> {
    const user = await this.db.user.findUniqueOrThrow({ where: { id: userId }, include: { profile: true } });
    return publicUser(user, user.profile!);
  }
}

const PRESENCE_ORDER = { in_game: 0, online: 1, offline: 2 } as const;

/** Favourites first, then who is playing, who is online, and by name. */
function byPresence(a: FriendDto, b: FriendDto): number {
  return Number(b.favorite) - Number(a.favorite) || PRESENCE_ORDER[a.presence] - PRESENCE_ORDER[b.presence] || a.name.localeCompare(b.name, 'ru');
}

/** https://… address of this server, without a trailing slash; empty when unknown. */
export function publicUrl(config: { PUBLIC_URL: string; RAILWAY_PUBLIC_DOMAIN: string }): string {
  const raw = config.PUBLIC_URL || (config.RAILWAY_PUBLIC_DOMAIN ? `https://${config.RAILWAY_PUBLIC_DOMAIN}` : '');
  return raw.replace(/\/+$/, '');
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
