import { randomUUID } from 'node:crypto';
import { clientMessageSchema } from '@arena/shared/schemas';
import type { AppErrorCode, ClientMessage, GameResultDto } from '@arena/shared';
import type { FastifyBaseLogger } from 'fastify';
import type { WebSocket } from 'ws';
import type { Config } from '../config.js';
import type { Db } from '../db.js';
import { AppError } from '../lib/errors.js';
import { metrics } from '../lib/metrics.js';
import type { Ledger } from '../services/ledger.js';
import { SettlementService } from '../services/settlement.js';
import type { UserService } from '../services/users.js';
import type { BotService } from '../services/bots.js';
import type { Alerts } from '../services/alerts.js';
import { GameManager, wsError } from './games.js';
import { Hub, type Client } from './hub.js';
import { RoomManager } from './rooms.js';
import type { SnapshotStore } from './store.js';
import type { DailyService } from '../services/daily.js';
import type { Brain } from '../brain/brain.js';

export interface RealtimeDeps {
  config: Config;
  db: Db;
  ledger: Ledger;
  users: UserService;
  store: SnapshotStore;
  log: FastifyBaseLogger;
  bots: BotService;
  /** How the strong bots think. */
  brain?: Brain;
  /** Daily quests are counted when a game is settled. */
  daily?: DailyService;
  alerts?: Alerts;
}

/** Wires the hub, rooms and games together and speaks the WebSocket protocol. */
const ORPHAN_AFTER_MS = 120_000;
/** How long a request id is remembered: a resend after a reconnect is answered, not applied again. */
const REPLY_TTL_MS = 5 * 60_000;
/** The game-runner lease: renewed every few seconds, lapses on its own if a server dies. */
const LEASE_TTL_MS = 10_000;
const LEASE_RENEW_MS = 3_000;
/** A new server waits this long at most for the old one to hand over the games. */
const HANDOVER_MAX_MS = 45_000;
/** Requests that only read: not worth remembering across a restart. */
const READ_ONLY = new Set(['PING', 'LOBBY_SUBSCRIBE', 'LOBBY_UNSUBSCRIBE', 'CHAT_SUBSCRIBE', 'CHAT_UNSUBSCRIBE', 'ROOM_WATCH', 'RECONNECT']);

export class Realtime {
  private sweeper: NodeJS.Timeout | null = null;
  /** Requests by «user + request id»: the outcome of each, finished or still running. */
  private readonly presenceListeners = new Set<(userIds: string[]) => void>();
  /** Settled games (casual and tournament): referral rewards and the like. */
  readonly finishedListeners = new Set<(result: GameResultDto) => void>();
  private readonly replies = new Map<string, { at: number; done: Promise<AppErrorCode | null> }>();
  readonly hub = new Hub();
  readonly rooms: RoomManager;
  readonly games: GameManager;
  readonly settlement: SettlementService;
  /** This server process (owner of the lease while it runs the games). */
  readonly instance = randomUUID();
  /** Resolves once this server holds the lease and has loaded rooms and games. */
  readonly ready: Promise<void>;
  private markReady!: () => void;
  private leaseTimer: NodeJS.Timeout | null = null;
  /** Set when the server is going down for an update: no new moves are taken. */
  private stopping = false;
  private readonly bootedAt = Date.now();
  /** Lease renewals in a row that failed (Redis unreachable). */
  private leaseErrors = 0;

  constructor(private readonly deps: RealtimeDeps) {
    this.ready = new Promise((resolve) => (this.markReady = resolve));
    this.settlement = new SettlementService(deps.db, deps.ledger, deps.config.RAKE_PERCENT, deps.daily);
    this.rooms = new RoomManager({ ...deps, hub: this.hub, games: () => this.games });
    this.games = new GameManager({
      db: deps.db,
      hub: this.hub,
      store: deps.store,
      ledger: deps.ledger,
      settlement: this.settlement,
      log: deps.log,
      onFinished: (roomId, result) => {
        this.rooms.finished(roomId, result);
        if (result) for (const l of this.finishedListeners) l(result);
      },
      onPresence: (ids) => this.emitPresence(ids),
      botLevel: () => deps.bots.level(),
      brain: deps.brain,
      alerts: deps.alerts,
    });
  }

  /**
   * Takes over the games. During a deploy the previous server still runs them for a few
   * seconds: wait until it hands the lease over (it does so when it stops), then load.
   */
  async start(): Promise<void> {
    const began = Date.now();
    const deadline = began + HANDOVER_MAX_MS;
    let waited = false;
    while (!(await this.deps.store.acquireLease(this.instance, LEASE_TTL_MS))) {
      waited = true;
      if (Date.now() > deadline) {
        this.deps.log.warn('previous server did not hand over the games in time; taking over');
        break;
      }
      await new Promise((r) => setTimeout(r, 500));
    }
    this.leaseTimer = setInterval(() => void this.renewLease(), LEASE_RENEW_MS);
    this.leaseTimer.unref();
    await this.recover();
    this.markReady();
    this.deps.log.info({ waitedMs: Date.now() - began, rooms: this.rooms.list().length, games: this.games.count() }, 'took over the tables');
    // The lease was still held and no clean stop was noted: the previous server died.
    const clean = await this.deps.store.takeHandover().catch(() => true);
    if (waited && !clean) {
      this.deps.alerts?.notice('crash', `Сервер перезапустился после сбоя: столы приняты, восстановлено игр — ${this.games.count()}.`);
    }
  }

  /** Keeps the lease; losing it means another server may run the same games — the owners hear at once. */
  private async renewLease(): Promise<void> {
    const store = this.deps.store;
    try {
      const held = (await store.renewLease(this.instance, LEASE_TTL_MS)) || (await store.acquireLease(this.instance, LEASE_TTL_MS));
      if (this.leaseErrors >= 3) this.deps.alerts?.resolve('lease', 'Связь с Redis восстановлена, столы снова под контролем.');
      this.leaseErrors = 0;
      if (!held && !this.stopping) {
        this.deps.alerts?.raise('lease-lost', 'Другой сервер забрал столы, пока этот ещё работает: проверьте, не запущено ли две копии Арены.');
      }
    } catch (error) {
      this.leaseErrors++;
      this.deps.log.warn({ err: error, errors: this.leaseErrors }, 'lease renewal failed');
      if (this.leaseErrors === 3) this.deps.alerts?.raise('lease', 'Redis недоступен: сервер не может продлить владение столами.', { err: error });
    }
  }

  /** Snapshot writes still waiting for Redis. */
  storeBacklog(): number {
    return this.deps.store.backlog ?? 0;
  }

  /**
   * Boot: bring back rooms and games from the snapshot store. Games that the database
   * still shows as running but that nobody can resume are aborted with refunds.
   */
  async recover(): Promise<void> {
    const { rooms, games } = await this.deps.store.loadAll();
    for (const room of rooms) this.rooms.restore(room);
    for (const game of games) {
      const room = rooms.find((r) => r.id === game.roomId);
      const players = (room?.seats ?? []).map((s) => ({ ...s, connected: false }));
      if (!room || players.length !== game.state.players.length) continue;
      await this.games.restore(game, players.map(({ userId, name, photoUrl, rating, premium, frame, crown, connected, bot }) => ({ userId, name, photoUrl, rating, premium, frame: frame ?? null, crown: crown ?? null, connected, bot: Boolean(bot) })));
    }
    // A table whose game could not come back (snapshot lost or expired) must not stay «playing»
    // forever: nobody could leave it or sit anywhere else. It waits for the next deal again (a
    // tournament match room is reopened by the tournament clock); the game itself is refunded
    // by the orphan sweep below.
    for (const room of rooms) {
      if (room.status === 'playing' && !(room.gameId && this.games.get(room.gameId))) {
        this.deps.log.warn({ roomId: room.id, gameId: room.gameId }, 'room had no game to resume; reset');
        this.rooms.finished(room.id, null);
      }
    }
    await this.sweepOrphans();
    this.sweeper = setInterval(() => void this.sweepOrphans().catch((e) => this.deps.log.error({ err: e }, 'orphan sweep failed')), 60_000);
    this.sweeper.unref();
  }

  /**
   * Games the database shows as running but nobody runs: refund them. A game counts as
   * abandoned only after two minutes without a move (turns time out after 30 s and moves are
   * logged every 2 s), so a game that another instance is still running — e.g. during a
   * rolling deploy — is never touched.
   */
  async sweepOrphans(now = Date.now()): Promise<void> {
    const running = await this.deps.db.game.findMany({
      where: { status: 'PLAYING' },
      select: { id: true, startedAt: true, moves: { orderBy: { seq: 'desc' }, take: 1, select: { createdAt: true } } },
    });
    for (const game of running) {
      if (this.games.get(game.id)) continue;
      const lastActivity = Math.max(game.startedAt.getTime(), game.moves[0]?.createdAt.getTime() ?? 0);
      if (now - lastActivity < ORPHAN_AFTER_MS) continue;
      await this.settlement.abort(game.id);
      metrics.inc('arena_games_aborted_total', 'Abandoned games refunded');
      this.deps.log.warn({ gameId: game.id }, 'aborted abandoned game, stakes refunded');
    }
  }

  /** Friends' lists follow who is online, playing or gone. */
  onPresence(listener: (userIds: string[]) => void): () => void {
    this.presenceListeners.add(listener);
    return () => this.presenceListeners.delete(listener);
  }

  private emitPresence(userIds: string[]): void {
    for (const l of this.presenceListeners) {
      try {
        l(userIds);
      } catch (error) {
        this.deps.log.error({ err: error }, 'presence listener failed');
      }
    }
  }

  /** «Был в сети»: friends see when someone was last here — refreshed on entry and on leaving. */
  private touch(userId: string): void {
    this.deps.db.user.update({ where: { id: userId }, data: { lastSeenAt: new Date() } }).catch(() => undefined);
  }

  async connect(userId: string, socket: WebSocket): Promise<Client> {
    // A socket that arrives during a hand-over waits until this server has the tables.
    await this.ready;
    const wasOnline = this.hub.isOnline(userId);
    const client = this.hub.attach(userId, socket);
    this.touch(userId);
    if (!wasOnline) this.emitPresence([userId]);
    const room = await this.rooms.connected(userId);
    if (room) {
      const game = room.gameId ? this.games.get(room.gameId) : undefined;
      this.hub.sendTo(client, { type: 'ROOM_UPDATED', room: this.rooms.dto(room) });
      // Back at the table: the state goes to everybody (so they see the player online again).
      if (game) await game.queue.run(() => game.presence(userId));
    }
    return client;
  }

  async disconnect(client: Client): Promise<void> {
    if (this.hub.detach(client)) {
      this.touch(client.userId);
      this.emitPresence([client.userId]);
      await this.rooms.disconnected(client.userId);
      const game = this.games.forUser(client.userId);
      if (game) await game.queue.run(() => game.presence(client.userId));
    }
  }

  async message(client: Client, raw: string): Promise<void> {
    let msg: ClientMessage;
    try {
      msg = clientMessageSchema.parse(JSON.parse(raw));
    } catch {
      return this.hub.sendTo(client, wsError('VALIDATION_FAILED'));
    }
    metrics.inc('arena_ws_messages_total', 'WebSocket messages received', { type: msg.type });
    // Going down for an update: the games are already settled, nothing more is applied.
    if (this.stopping && msg.type !== 'PING') return this.hub.sendTo(client, wsError('SERVER_RESTARTING', msg.rid));
    // Answer with the rid so the client knows this exact request was dropped and may retry.
    if (!this.hub.allow(client)) return this.hub.sendTo(client, wsError('RATE_LIMITED', msg.rid));

    // A resent request (double tap, or a resend after the network came back — even on a new
    // socket) gets the answer of the first one and is never applied twice. Ids «page:n» are
    // unique per app launch, so they are remembered per user; older plain ids per connection.
    const lasting = Boolean(msg.rid?.includes(':')) && !READ_ONLY.has(msg.type);
    const key = msg.rid ? (msg.rid.includes(':') ? `${client.userId}|${msg.rid}` : `#${client.id}|${msg.rid}`) : null;
    let earlier = key ? this.replies.get(key) : undefined;
    // Just after a restart: the request may have been applied by the previous server, whose
    // answer the app never got. Those ids are in the store.
    if (!earlier && key && lasting && Date.now() - this.bootedAt < REPLY_TTL_MS && (await this.deps.store.hasReply(key))) {
      metrics.inc('arena_ws_duplicates_total', 'Resent requests answered without applying them again');
      return this.reply(client, msg.rid, null);
    }
    earlier ??= key ? this.replies.get(key) : undefined;
    if (earlier) {
      metrics.inc('arena_ws_duplicates_total', 'Resent requests answered without applying them again');
      return this.reply(client, msg.rid, await earlier.done);
    }
    const done = this.dispatch(client, msg).then(
      () => null,
      (error: unknown): AppErrorCode => {
        const code: AppErrorCode = error instanceof AppError ? error.code : 'SERVER_ERROR';
        metrics.inc('arena_ws_errors_total', 'Rejected WebSocket requests by error code', { code });
        if (!(error instanceof AppError)) this.deps.log.error({ err: error, type: msg.type }, 'ws handler failed');
        return code;
      },
    );
    if (key) this.remember(key, done);
    const code = await done;
    // A refused request changed nothing, so trying it again is allowed.
    if (code && key) this.replies.delete(key);
    else if (key && lasting) void this.deps.store.saveReply(key, REPLY_TTL_MS);
    this.reply(client, msg.rid, code);
  }

  private reply(client: Client, rid: string | undefined, code: AppErrorCode | null): void {
    if (code) this.hub.sendTo(client, wsError(code, rid));
    else if (rid) this.hub.sendTo(client, { type: 'ACK', rid });
  }

  private remember(key: string, done: Promise<AppErrorCode | null>): void {
    const now = Date.now();
    this.replies.set(key, { at: now, done });
    // Oldest first (insertion order): drop what has expired.
    for (const [k, v] of this.replies) {
      if (now - v.at < REPLY_TTL_MS && this.replies.size < 50_000) break;
      this.replies.delete(k);
    }
  }

  private async dispatch(client: Client, msg: ClientMessage): Promise<void> {
    const { userId } = client;
    switch (msg.type) {
      case 'PING':
        return this.hub.sendTo(client, { type: 'PONG', rid: msg.rid, serverTime: Date.now() });
      case 'LOBBY_SUBSCRIBE':
        return this.hub.subscribeLobby(client, msg.filter, this.rooms.list());
      case 'LOBBY_UNSUBSCRIBE':
        return this.hub.unsubscribeLobby(client);
      case 'CHAT_SUBSCRIBE':
        return this.hub.setChat(client, true);
      case 'CHAT_UNSUBSCRIBE':
        return this.hub.setChat(client, false);
      case 'ROOM_WATCH':
      case 'RECONNECT': {
        const room = this.rooms.get(msg.roomId);
        if (!room || !room.seats.some((s) => s.userId === userId)) throw new AppError('NOT_FOUND');
        this.hub.sendTo(client, { type: 'ROOM_UPDATED', room: this.rooms.dto(room) });
        if (room.gameId) this.games.get(room.gameId)?.sendState(userId);
        return;
      }
      case 'READY':
        return this.rooms.setReady(userId, msg.roomId, msg.ready);
      case 'ROOM_EMOJI':
        return this.rooms.emoji(userId, msg.roomId, msg.emoji);
      case 'MOVE_SEAT':
        return this.rooms.moveSeat(userId, msg.roomId, msg.seat);
      case 'SEAT_SWAP':
        return this.rooms.askSwap(userId, msg.roomId, msg.userId);
      case 'SEAT_SWAP_ANSWER':
        return this.rooms.answerSwap(userId, msg.roomId, msg.userId, msg.accept);
      default:
        return this.games.handle(userId, msg);
    }
  }

  /** A banned player: gives up a running game, leaves any table and is disconnected. */
  async expel(userId: string): Promise<void> {
    const game = this.games.forUser(userId);
    if (game) await this.games.handle(userId, { type: 'LEAVE_GAME', gameId: game.id }).catch(() => undefined);
    const room = this.rooms.roomOf(userId);
    if (room && room.status === 'waiting') await this.rooms.leave(userId, room.id).catch(() => undefined);
    this.hub.kick(userId);
  }

  /**
   * Going down (an update or a restart). Everyone is told; every casual game is cancelled
   * with all stakes returned and its players stay seated at the table for the next deal on
   * the new server. Tournament games are saved and resumed by the new server instead (a
   * bracket match cannot be refunded). Then the lease goes to the next server.
   */
  /** Tests only: shut down like a crash (games are left in the store for the next server). */
  crashOnShutdown = false;

  async stopForRestart(): Promise<void> {
    if (this.stopping || this.crashOnShutdown) return;
    this.stopping = true;
    if (this.sweeper) clearInterval(this.sweeper);
    this.hub.broadcast({ type: 'SERVER_RESTART', refunded: this.games.liveCasual(this.rooms) > 0 });
    const cancelled = await this.games.cancelForRestart(this.rooms);
    if (cancelled) this.deps.log.info({ games: cancelled }, 'games cancelled for the restart, stakes refunded');
    await this.rooms.drain();
  }

  async shutdown(): Promise<void> {
    await this.stopForRestart();
    if (this.leaseTimer) clearInterval(this.leaseTimer);
    this.rooms.shutdown();
    await this.games.shutdown();
    if (!this.crashOnShutdown) {
      // The next server reads the snapshots: the last ones must have landed.
      await this.deps.store.flush?.(5_000);
      await this.deps.store.markHandover().catch(() => undefined);
      await this.deps.store.releaseLease(this.instance).catch(() => undefined);
      this.deps.log.info('handed the tables over to the next server');
    }
    this.hub.closeAll();
    await this.deps.store.close();
  }
}
