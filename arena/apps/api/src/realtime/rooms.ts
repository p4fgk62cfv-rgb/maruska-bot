import { validateSettings } from '@arena/game-engine';
import {
  isPremium,
  roomDeepLink,
  STAKE_OPTIONS,
  type AppErrorCode,
  type GameResultDto,
  type MyRoomDto,
  type RoomDto,
  type RoomSettings,
} from '@arena/shared';
import type { FastifyBaseLogger } from 'fastify';
import type { Config } from '../config.js';
import type { Db } from '../db.js';
import { AppError } from '../lib/errors.js';
import { checkInvite, hashPassword, inviteCode, newRoomId, verifyPassword } from '../lib/ids.js';
import { SerialQueue } from '../lib/serial.js';
import { ShortOfFunds } from '../services/settlement.js';
import type { UserService } from '../services/users.js';
import type { GameManager } from './games.js';
import type { Hub } from './hub.js';
import type { SnapshotStore } from './store.js';
import { assertSmile } from './smiles.js';
import type { Room, RoomConfig, Seat } from './types.js';

/** Full rooms wait this long for everyone to press «Готов»; then the slow ones are removed. */
export const READY_TIMEOUT_MS = 30_000;
/** A player who drops out of a waiting room keeps the seat this long. */
export const WAITING_GRACE_MS = 30_000;
/** After a deal the same company has this long to press «Готов» for the next one (the result screen eats some of it). */
export const REMATCH_READY_MS = 180_000;
const EMOJI_COOLDOWN_MS = 1500;
/** Wrong private-table PINs: after this many in the window the table stops accepting guesses. */
const PIN_TRIES = 8;
const PIN_WINDOW_MS = 10 * 60_000;

/** Callbacks into the tournament service for match rooms. */
export interface MatchHooks {
  finished(room: Room, result: GameResultDto | null): void;
  /** The ready timer ran out; `ready` are the players who did press «Готов». */
  noShow(room: Room, ready: string[]): void;
  forfeit(room: Room, userId: string): void;
}

export interface RoomDeps {
  config: Config;
  db: Db;
  hub: Hub;
  store: SnapshotStore;
  users: UserService;
  games: () => GameManager;
  log: FastifyBaseLogger;
}

const QUICK_DEFAULTS = {
  players: 2,
  deckSize: 36,
  speed: 'normal',
  variant: 'podkidnoy',
  throwIn: 'all',
  fairness: 'fair',
  ending: 'classic',
} as const;

export class RoomManager {
  private readonly rooms = new Map<string, Room>();
  private readonly queues = new Map<string, SerialQueue>();
  private readonly timers = new Map<string, NodeJS.Timeout>();
  private readonly lastEmoji = new Map<string, number>();
  /** One table at a time: a player's create/join/quick run one after another, so a double tap cannot seat them twice. */
  private readonly userQueues = new Map<string, { queue: SerialQueue; pending: number }>();
  private readonly pinFails = new Map<string, { count: number; since: number }>();
  matchHooks: MatchHooks | null = null;

  constructor(private readonly deps: RoomDeps) {}

  // ── queries ────────────────────────────────────────────────

  list(): RoomDto[] {
    return [...this.rooms.values()].map((r) => this.dto(r)).sort(lobbyOrder);
  }

  get(id: string): Room | undefined {
    return this.rooms.get(id);
  }

  roomOf(userId: string): Room | undefined {
    for (const room of this.rooms.values()) if (room.seats.some((s) => s.userId === userId)) return room;
    return undefined;
  }

  dto(room: Room): RoomDto {
    return {
      id: room.id,
      server: room.server,
      status: room.status,
      ownerId: room.ownerId,
      isPrivate: room.isPrivate,
      settings: room.settings,
      seats: room.seats.map((s, seat) => ({ seat, ...s })),
      gameId: room.gameId,
      createdAt: room.createdAt,
      premium: room.seats.some((s) => s.premium),
      readyDeadline: room.readyDeadline,
      tournament: room.tournament ? { id: room.tournament.id, title: room.tournament.title, round: room.tournament.round } : null,
    };
  }

  mine(room: Room): MyRoomDto {
    const code = inviteCode(room.id, this.deps.config.SESSION_SECRET);
    const link = roomDeepLink(this.deps.config.BOT_USERNAME || 'bot', this.deps.config.MINI_APP_SHORT_NAME || null, room.id, code);
    const text = `Сыграем в дурака? Ставка ${room.settings.stake}`;
    return {
      room: this.dto(room),
      invite: { link, shareUrl: `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}` },
    };
  }

  onlineByServer(): Record<string, number> {
    const counts: Record<string, number> = {};
    for (const room of this.rooms.values()) {
      counts[room.server] = (counts[room.server] ?? 0) + room.seats.filter((s) => s.connected).length;
    }
    return counts;
  }

  // ── commands ───────────────────────────────────────────────

  create(userId: string, settings: RoomSettings): Promise<MyRoomDto> {
    return this.asUser(userId, () => this.createRoom(userId, settings));
  }

  join(userId: string, roomId: string, access: { password?: string; invite?: string }): Promise<MyRoomDto> {
    return this.asUser(userId, () => this.joinRoom(userId, roomId, access));
  }

  /** «Быстрая игра»: the fullest open room the player can afford, or a new one. */
  quick(userId: string, stake?: number): Promise<MyRoomDto> {
    return this.asUser(userId, () => this.quickRoom(userId, stake));
  }

  private async asUser<T>(userId: string, job: () => Promise<T>): Promise<T> {
    let entry = this.userQueues.get(userId);
    if (!entry) {
      entry = { queue: new SerialQueue(), pending: 0 };
      this.userQueues.set(userId, entry);
    }
    entry.pending++;
    try {
      return await entry.queue.run(job);
    } finally {
      if (--entry.pending === 0) this.userQueues.delete(userId);
    }
  }

  private async createRoom(userId: string, settings: RoomSettings): Promise<MyRoomDto> {
    const problem = validateSettings(settings);
    if (problem) throw new AppError(problem === 'DECK_NOT_SUPPORTED' ? 'DECK_NOT_SUPPORTED' : 'VALIDATION_FAILED');
    if (settings.isPrivate && !settings.password) throw new AppError('VALIDATION_FAILED');

    await this.leaveWaitingRoomOf(userId);
    const seat = await this.seatFor(userId, settings.stake);
    const room: Room = {
      id: newRoomId(),
      server: settings.server,
      ownerId: userId,
      isPrivate: settings.isPrivate,
      passwordHash: settings.isPrivate && settings.password ? await hashPassword(settings.password) : null,
      settings: {
        stake: settings.stake,
        players: settings.players,
        deckSize: settings.deckSize,
        speed: settings.speed,
        variant: settings.variant,
        throwIn: settings.throwIn,
        fairness: settings.fairness,
        ending: settings.ending,
      },
      status: 'waiting',
      seats: [seat],
      gameId: null,
      createdAt: Date.now(),
      readyDeadline: null,
    };
    await this.deps.db.room.create({
      data: {
        id: room.id,
        server: room.server,
        ownerId: userId,
        isPrivate: room.isPrivate,
        passwordHash: room.passwordHash,
        stake: BigInt(room.settings.stake),
        maxPlayers: room.settings.players,
        deckSize: room.settings.deckSize,
        speed: room.settings.speed,
        variant: room.settings.variant,
        throwIn: room.settings.throwIn,
        fairness: room.settings.fairness,
        ending: room.settings.ending,
      },
    });
    this.rooms.set(room.id, room);
    await this.changed(room, true);
    return this.mine(room);
  }

  private async joinRoom(userId: string, roomId: string, access: { password?: string; invite?: string }): Promise<MyRoomDto> {
    const room = this.rooms.get(roomId);
    if (!room) throw new AppError('ROOM_CLOSED');
    if (room.seats.some((s) => s.userId === userId)) return this.mine(room);

    await this.leaveWaitingRoomOf(userId);
    return this.queue(roomId).run(async () => {
      if (room.status !== 'waiting') throw new AppError(room.status === 'playing' ? 'GAME_ALREADY_STARTED' : 'ROOM_CLOSED');
      if (room.seats.length >= room.settings.players) throw new AppError('ROOM_FULL');
      if (room.passwordHash) {
        const byInvite = access.invite ? checkInvite(room.id, access.invite, this.deps.config.SESSION_SECRET) : false;
        if (!byInvite) {
          // A PIN is short: after a series of wrong guesses the table only lets in by invite link.
          const fails = this.pinFails.get(room.id);
          const now = Date.now();
          if (fails && now - fails.since < PIN_WINDOW_MS && fails.count >= PIN_TRIES) throw new AppError('RATE_LIMITED');
          const byPassword = access.password ? await verifyPassword(access.password, room.passwordHash) : false;
          if (!byPassword) {
            const fresh = !fails || now - fails.since >= PIN_WINDOW_MS;
            this.pinFails.set(room.id, fresh ? { count: 1, since: now } : { ...fails, count: fails.count + 1 });
            throw new AppError('WRONG_PASSWORD');
          }
        }
      }
      const seat = await this.seatFor(userId, room.settings.stake);
      // Re-check after the awaits: someone else may have taken the last seat.
      if (room.seats.length >= room.settings.players) throw new AppError('ROOM_FULL');
      if (room.status !== 'waiting') throw new AppError('GAME_ALREADY_STARTED');
      const elsewhere = this.roomOf(userId);
      if (elsewhere && elsewhere !== room) throw new AppError('ALREADY_IN_ROOM');
      room.seats.push(seat);
      if (room.seats.length === room.settings.players) this.armReadyTimer(room);
      await this.changed(room);
      for (const s of room.seats) this.deps.hub.send(s.userId, { type: 'ROOM_JOINED', room: this.dto(room), userId });
      return this.mine(room);
    });
  }

  private async quickRoom(userId: string, stake?: number): Promise<MyRoomDto> {
    const existing = this.roomOf(userId);
    if (existing) return this.mine(existing);
    const balance = (await this.deps.users.wallet(userId)).credits;
    const affordable = STAKE_OPTIONS.filter((s) => s <= balance);
    if (!affordable.length) throw new AppError('INSUFFICIENT_FUNDS');
    const wanted = stake && (affordable as number[]).includes(stake) ? stake : null;

    const candidates = this.list()
      .filter((r) => r.status === 'waiting' && !r.isPrivate && r.seats.length < r.settings.players)
      .filter((r) => (wanted ? r.settings.stake === wanted : r.settings.stake <= balance))
      .sort((a, b) => b.seats.length / b.settings.players - a.seats.length / a.settings.players);
    for (const room of candidates) {
      try {
        return await this.joinRoom(userId, room.id, {});
      } catch (error) {
        if (!(error instanceof AppError)) throw error;
      }
    }
    return this.createRoom(userId, {
      ...QUICK_DEFAULTS,
      stake: wanted ?? affordable[0]!,
      server: 'almaz',
      isPrivate: false,
    });
  }

  async leave(userId: string, roomId: string): Promise<void> {
    const room = this.rooms.get(roomId);
    if (!room) return;
    await this.queue(roomId).run(async () => {
      if (room.status === 'playing') throw new AppError('GAME_ALREADY_STARTED');
      if (room.tournament) {
        if (!room.seats.some((s) => s.userId === userId)) return;
        // Walking out of a match hands it to the opponent.
        this.matchHooks?.forfeit(room, userId);
        await this.closeRoom(room);
        return;
      }
      await this.removeSeat(room, userId);
    });
  }

  /**
   * Tournament match: both players are seated by the server. A player waiting at a casual
   * table is moved out of it; a player still in a running game makes this throw (retry later).
   */
  async createMatchRoom(
    tournament: { id: string; title: string; round: number; matchId: string },
    userIds: [string, string],
    settings: Omit<RoomConfig, 'stake' | 'players'>,
  ): Promise<Room> {
    for (const userId of userIds) {
      const current = this.roomOf(userId);
      if (!current) continue;
      if (current.status !== 'waiting' || current.tournament) throw new AppError('ALREADY_IN_ROOM');
      await this.leave(userId, current.id);
    }
    const seats = await Promise.all(userIds.map((id) => this.seatFor(id, 0)));
    const room: Room = {
      id: newRoomId(),
      server: 'almaz',
      ownerId: userIds[0],
      isPrivate: true,
      passwordHash: null,
      settings: { ...settings, stake: 0, players: 2 },
      status: 'waiting',
      seats,
      gameId: null,
      createdAt: Date.now(),
      readyDeadline: null,
      tournament,
    };
    await this.deps.db.room.create({
      data: {
        id: room.id,
        server: room.server,
        ownerId: room.ownerId,
        isPrivate: true,
        stake: 0n,
        maxPlayers: 2,
        deckSize: settings.deckSize,
        speed: settings.speed,
        variant: settings.variant,
        throwIn: settings.throwIn,
        fairness: settings.fairness,
        ending: settings.ending,
      },
    });
    this.rooms.set(room.id, room);
    this.armReadyTimer(room, this.deps.config.MATCH_READY_SECONDS * 1000);
    await this.changed(room);
    return room;
  }

  /** Moderator: close a table that is still waiting for players (no stakes were taken yet). */
  async adminClose(roomId: string): Promise<boolean> {
    const room = this.rooms.get(roomId);
    if (!room || room.status !== 'waiting' || room.tournament) return false;
    await this.queue(roomId).run(() => this.closeRoom(room));
    return true;
  }

  /** Removes a room and everyone in it (used for tournament matches that end without a game). */
  private async closeRoom(room: Room): Promise<void> {
    this.clearTimer(`ready:${room.id}`);
    room.status = 'closed';
    this.forget(room.id);
    for (const s of room.seats) this.deps.hub.send(s.userId, { type: 'ROOM_LEFT', room: this.dto(room), userId: s.userId });
    await this.deps.store.deleteRoom(room.id).catch(() => undefined);
    await this.deps.db.room.update({ where: { id: room.id }, data: { status: 'CLOSED', closedAt: new Date() } }).catch(() => undefined);
  }

  async setReady(userId: string, roomId: string, ready: boolean): Promise<void> {
    const room = this.rooms.get(roomId);
    if (!room) throw new AppError('ROOM_CLOSED');
    await this.queue(roomId).run(async () => {
      const seat = room.seats.find((s) => s.userId === userId);
      if (!seat) throw new AppError('FORBIDDEN');
      if (room.status !== 'waiting') return;
      seat.ready = ready;
      await this.changed(room);
      if (room.seats.length === room.settings.players && room.seats.every((s) => s.ready)) await this.startGame(room);
    });
  }

  /** Smiles work at a gathering table too, not only during a deal. */
  async emoji(userId: string, roomId: string, emoji: string): Promise<void> {
    const room = this.rooms.get(roomId);
    if (!room || !room.seats.some((s) => s.userId === userId)) throw new AppError('FORBIDDEN');
    const now = Date.now();
    if (now - (this.lastEmoji.get(userId) ?? 0) < EMOJI_COOLDOWN_MS) throw new AppError('RATE_LIMITED');
    this.lastEmoji.set(userId, now);
    if (this.lastEmoji.size > 5000) for (const [id, at] of this.lastEmoji) if (now - at > EMOJI_COOLDOWN_MS) this.lastEmoji.delete(id);
    await assertSmile(this.deps.db, userId, emoji);
    for (const s of room.seats) this.deps.hub.send(s.userId, { type: 'EMOJI', gameId: null, roomId, userId, emoji });
  }

  // ── connections ────────────────────────────────────────────

  async connected(userId: string): Promise<Room | undefined> {
    const room = this.roomOf(userId);
    if (!room) return undefined;
    this.clearTimer(`grace:${userId}`);
    await this.queue(room.id).run(async () => {
      const seat = room.seats.find((s) => s.userId === userId);
      if (!seat || seat.connected) return;
      seat.connected = true;
      await this.changed(room);
      for (const s of room.seats) {
        if (s.userId !== userId) this.deps.hub.send(s.userId, { type: 'PLAYER_RECONNECTED', roomId: room.id, userId });
      }
    });
    return room;
  }

  async disconnected(userId: string): Promise<void> {
    const room = this.roomOf(userId);
    if (!room) return;
    const graceUntil = Date.now() + WAITING_GRACE_MS;
    await this.queue(room.id).run(async () => {
      const seat = room.seats.find((s) => s.userId === userId);
      if (!seat) return;
      seat.connected = false;
      await this.changed(room);
      for (const s of room.seats) {
        if (s.userId !== userId) this.deps.hub.send(s.userId, { type: 'PLAYER_DISCONNECTED', roomId: room.id, userId, graceUntil });
      }
    });
    // In a waiting room an absent player would block everybody; in a game the turn timer handles it.
    // Tournament matches have their own (longer) no-show timer.
    if (room.status === 'waiting' && !room.tournament) {
      this.setTimer(`grace:${userId}`, WAITING_GRACE_MS, () =>
        this.queue(room.id).run(async () => {
          const seat = room.seats.find((s) => s.userId === userId);
          if (seat && !seat.connected && room.status === 'waiting') await this.removeSeat(room, userId);
        }),
      );
    }
  }

  // ── game lifecycle ─────────────────────────────────────────

  private async startGame(room: Room): Promise<void> {
    this.clearTimer(`ready:${room.id}`);
    room.readyDeadline = null;
    room.status = 'playing';
    try {
      const runner = await this.deps.games().start(room);
      room.gameId = runner.id;
      await this.changed(room);
    } catch (error) {
      room.status = 'waiting';
      for (const s of room.seats) s.ready = false;
      if (error instanceof ShortOfFunds) {
        this.deps.hub.send(error.userId, { type: 'ERROR', code: 'INSUFFICIENT_FUNDS', message: 'Недостаточно кредитов для ставки.' });
        await this.removeSeat(room, error.userId);
      } else {
        this.deps.log.error({ err: error, roomId: room.id }, 'game start failed');
        for (const s of room.seats) this.deps.hub.send(s.userId, { type: 'ERROR', code: 'SERVER_ERROR', message: 'Не удалось начать игру.' });
      }
      await this.changed(room);
    }
  }

  /**
   * Called by the game when it is settled. A tournament match room closes; a casual table
   * stays together: it waits again, and when everyone presses «Готов» the next deal starts.
   * Whoever does not want another round leaves; whoever is gone loses the seat after the grace.
   */
  finished(roomId: string, result: GameResultDto | null): void {
    const room = this.rooms.get(roomId);
    if (!room) return;
    if (room.tournament) {
      this.matchHooks?.finished(room, result);
      room.status = 'finished';
      this.forget(roomId);
      this.deps.store.deleteRoom(roomId).catch(() => undefined);
      this.deps.hub.publishRoom(this.dto(room));
      return;
    }
    this.queue(roomId)
      .run(async () => {
        room.status = 'waiting';
        room.gameId = null;
        room.readyDeadline = null;
        for (const s of room.seats) {
          s.ready = false;
          s.connected = this.deps.hub.isOnline(s.userId);
        }
        for (const s of room.seats) {
          if (!s.connected) this.setTimer(`grace:${s.userId}`, WAITING_GRACE_MS, () => this.queue(room.id).run(() => this.dropIfAway(room, s.userId)));
        }
        if (room.seats.length === room.settings.players) this.armReadyTimer(room, REMATCH_READY_MS);
        await this.changed(room);
      })
      .catch((error) => this.deps.log.error({ err: error, roomId }, 'rematch reset failed'));
  }

  restore(room: Room): void {
    for (const s of room.seats) s.connected = false;
    this.rooms.set(room.id, room);
    if (room.tournament && room.status === 'waiting') {
      this.armReadyTimer(room, this.deps.config.MATCH_READY_SECONDS * 1000);
      return;
    }
    if (room.status === 'waiting') {
      for (const s of room.seats) this.setTimer(`grace:${s.userId}`, WAITING_GRACE_MS, () => this.queue(room.id).run(() => this.dropIfAway(room, s.userId)));
    }
  }

  private async dropIfAway(room: Room, userId: string): Promise<void> {
    const seat = room.seats.find((s) => s.userId === userId);
    if (seat && !seat.connected && room.status === 'waiting') await this.removeSeat(room, userId);
  }

  // ── helpers ────────────────────────────────────────────────

  private async seatFor(userId: string, stake: number): Promise<Seat> {
    const me = await this.deps.users.me(userId);
    if (!me) throw new AppError('UNAUTHORIZED');
    if (me.wallet.credits < stake) throw new AppError('INSUFFICIENT_FUNDS');
    return {
      userId,
      name: me.name,
      photoUrl: me.photoUrl,
      rating: me.rating,
      premium: isPremium(me.premiumUntil ? Date.parse(me.premiumUntil) : null, Date.now()),
      frame: me.equipped.frame,
      crown: me.equipped.crown,
      ready: false,
      connected: this.deps.hub.isOnline(userId),
    };
  }

  /** One table at a time: joining elsewhere quietly leaves a waiting room, but never a running game. */
  private async leaveWaitingRoomOf(userId: string): Promise<void> {
    const current = this.roomOf(userId);
    if (!current) return;
    if (current.status !== 'waiting' || current.tournament) throw new AppError('ALREADY_IN_ROOM');
    await this.leave(userId, current.id);
  }

  private async removeSeat(room: Room, userId: string): Promise<void> {
    const before = room.seats.length;
    room.seats = room.seats.filter((s) => s.userId !== userId);
    if (room.seats.length === before) return;
    this.clearTimer(`grace:${userId}`);
    for (const s of room.seats) s.ready = false;
    this.clearTimer(`ready:${room.id}`);
    room.readyDeadline = null;
    this.deps.hub.send(userId, { type: 'ROOM_LEFT', room: this.dto(room), userId });
    for (const s of room.seats) this.deps.hub.send(s.userId, { type: 'ROOM_LEFT', room: this.dto(room), userId });

    if (room.seats.length === 0) {
      room.status = 'closed';
      this.forget(room.id);
      await this.deps.store.deleteRoom(room.id).catch(() => undefined);
      await this.deps.db.room.update({ where: { id: room.id }, data: { status: 'CLOSED', closedAt: new Date() } }).catch(() => undefined);
      this.deps.hub.publishRoom(this.dto(room));
      return;
    }
    if (room.ownerId === userId) room.ownerId = room.seats[0]!.userId;
    await this.changed(room);
  }

  /** A room is gone: drop everything kept for it. Jobs already queued still finish. */
  private forget(roomId: string): void {
    this.rooms.delete(roomId);
    this.queues.delete(roomId);
    this.pinFails.delete(roomId);
    this.clearTimer(`ready:${roomId}`);
  }

  private armReadyTimer(room: Room, ms = READY_TIMEOUT_MS): void {
    room.readyDeadline = Date.now() + ms;
    this.setTimer(`ready:${room.id}`, ms, () =>
      this.queue(room.id).run(async () => {
        if (room.status !== 'waiting' || !this.rooms.has(room.id)) return;
        room.readyDeadline = null;
        if (room.tournament) {
          this.matchHooks?.noShow(room, room.seats.filter((s) => s.ready).map((s) => s.userId));
          await this.closeRoom(room);
          return;
        }
        for (const s of room.seats.filter((seat) => !seat.ready)) await this.removeSeat(room, s.userId);
      }),
    );
  }

  /** Persist + tell the lobby and everyone in the room. */
  private async changed(room: Room, created = false): Promise<void> {
    await this.deps.store.saveRoom(room).catch((error) => this.deps.log.error({ err: error }, 'room snapshot failed'));
    const dto = this.dto(room);
    this.deps.hub.publishRoom(dto, created);
    for (const s of room.seats) this.deps.hub.send(s.userId, { type: 'ROOM_UPDATED', room: dto });
  }

  private queue(roomId: string): SerialQueue {
    let q = this.queues.get(roomId);
    if (!q) {
      q = new SerialQueue();
      this.queues.set(roomId, q);
    }
    return q;
  }

  private setTimer(key: string, ms: number, job: () => Promise<unknown>): void {
    this.clearTimer(key);
    const timer = setTimeout(() => {
      this.timers.delete(key);
      job().catch((error) => this.deps.log.error({ err: error, key }, 'room timer failed'));
    }, ms);
    timer.unref();
    this.timers.set(key, timer);
  }

  private clearTimer(key: string): void {
    const timer = this.timers.get(key);
    if (timer) clearTimeout(timer);
    this.timers.delete(key);
  }

  shutdown(): void {
    for (const timer of this.timers.values()) clearTimeout(timer);
    this.timers.clear();
  }
}

/** Premium tables first, then the fullest, then the newest. */
function lobbyOrder(a: RoomDto, b: RoomDto): number {
  if (a.premium !== b.premium) return a.premium ? -1 : 1;
  const fill = b.seats.length / b.settings.players - a.seats.length / a.settings.players;
  return fill !== 0 ? fill : b.createdAt - a.createdAt;
}

export type { AppErrorCode };
