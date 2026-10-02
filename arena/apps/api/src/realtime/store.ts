import { Redis } from 'ioredis';
import type { FastifyBaseLogger } from 'fastify';
import { metrics } from '../lib/metrics.js';
import type { Alerts } from '../services/alerts.js';
import type { GameSnapshot, Room } from './types.js';

/**
 * Where live rooms and games survive a restart. The authoritative copy is in the
 * process memory; the store is written after every change and read once at boot.
 */
export interface SnapshotStore {
  saveRoom(room: Room): Promise<void>;
  deleteRoom(id: string): Promise<void>;
  saveGame(game: GameSnapshot): Promise<void>;
  deleteGame(id: string): Promise<void>;
  loadAll(): Promise<{ rooms: Room[]; games: GameSnapshot[] }>;
  /**
   * Who runs the live games. During a deploy the old and the new server overlap for a few
   * seconds; only the holder of this lease may load and run games, so they never run twice.
   */
  acquireLease(owner: string, ttlMs: number): Promise<boolean>;
  renewLease(owner: string, ttlMs: number): Promise<boolean>;
  releaseLease(owner: string): Promise<void>;
  /**
   * Request ids the server already applied, kept across a restart: an app that resends its
   * last move to the next server gets «done», not a second move.
   */
  saveReply(key: string, ttlMs: number): Promise<void>;
  hasReply(key: string): Promise<boolean>;
  /** A clean stop leaves this note; the next server finding none knows the last one crashed. */
  markHandover(): Promise<void>;
  /** Reads and clears the note. */
  takeHandover(): Promise<boolean>;
  /** Writes that failed and wait for a retry (ResilientStore). */
  readonly backlog?: number;
  /** Lands every waiting write, or gives up after `maxMs` (ResilientStore). */
  flush?(maxMs?: number): Promise<boolean>;
  /** Survives restarts: true when this store is shared/persistent (Redis). */
  readonly durable: boolean;
  ping(): Promise<void>;
  close(): Promise<void>;
}

export class MemoryStore implements SnapshotStore {
  readonly durable = false;
  private rooms = new Map<string, Room>();
  private games = new Map<string, GameSnapshot>();
  private replies = new Map<string, number>();

  async saveRoom(room: Room) {
    this.rooms.set(room.id, structuredClone(room));
  }
  async deleteRoom(id: string) {
    this.rooms.delete(id);
  }
  async saveGame(game: GameSnapshot) {
    this.games.set(game.gameId, structuredClone(game));
  }
  async deleteGame(id: string) {
    this.games.delete(id);
  }
  async loadAll() {
    return { rooms: [...this.rooms.values()], games: [...this.games.values()] };
  }
  async acquireLease() {
    return true;
  }
  async renewLease() {
    return true;
  }
  async releaseLease() {}
  async saveReply(key: string, ttlMs: number) {
    this.replies.set(key, Date.now() + ttlMs);
  }
  async hasReply(key: string) {
    return (this.replies.get(key) ?? 0) > Date.now();
  }
  async markHandover() {}
  async takeHandover() {
    return true;
  }
  async ping() {}
  async close() {}
}

const ROOMS = 'arena:rooms';
const GAMES = 'arena:games';
/** Snapshots of abandoned rooms/games expire on their own. */
const TTL_SECONDS = 24 * 3600;
const LEASE = 'arena:lease';

export class RedisStore implements SnapshotStore {
  readonly durable = true;
  private readonly redis: Redis;

  constructor(url: string) {
    this.redis = new Redis(url, { maxRetriesPerRequest: 3, lazyConnect: false });
  }

  async saveRoom(room: Room) {
    await this.redis.multi().set(`arena:room:${room.id}`, JSON.stringify(room), 'EX', TTL_SECONDS).sadd(ROOMS, room.id).exec();
  }
  async deleteRoom(id: string) {
    await this.redis.multi().del(`arena:room:${id}`).srem(ROOMS, id).exec();
  }
  async saveGame(game: GameSnapshot) {
    await this.redis.multi().set(`arena:game:${game.gameId}`, JSON.stringify(game), 'EX', TTL_SECONDS).sadd(GAMES, game.gameId).exec();
  }
  async deleteGame(id: string) {
    await this.redis.multi().del(`arena:game:${id}`).srem(GAMES, id).exec();
  }
  async loadAll() {
    const load = async <T>(set: string, prefix: string): Promise<T[]> => {
      const ids = await this.redis.smembers(set);
      if (!ids.length) return [];
      const values = await this.redis.mget(ids.map((id) => `${prefix}${id}`));
      const stale = ids.filter((_, i) => !values[i]);
      if (stale.length) await this.redis.srem(set, ...stale);
      return values.filter((v): v is string => Boolean(v)).map((v) => JSON.parse(v) as T);
    };
    return { rooms: await load<Room>(ROOMS, 'arena:room:'), games: await load<GameSnapshot>(GAMES, 'arena:game:') };
  }
  async acquireLease(owner: string, ttlMs: number) {
    return (await this.redis.set(LEASE, owner, 'PX', ttlMs, 'NX')) === 'OK';
  }
  async renewLease(owner: string, ttlMs: number) {
    const done = await this.redis.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('pexpire', KEYS[1], ARGV[2]) else return 0 end", 1, LEASE, owner, String(ttlMs));
    return done === 1;
  }
  async releaseLease(owner: string) {
    await this.redis.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end", 1, LEASE, owner);
  }
  async saveReply(key: string, ttlMs: number) {
    await this.redis.set(`arena:reply:${key}`, '1', 'PX', ttlMs);
  }
  async hasReply(key: string) {
    return (await this.redis.exists(`arena:reply:${key}`)) === 1;
  }
  async markHandover() {
    await this.redis.set('arena:handover', '1', 'EX', 600);
  }
  async takeHandover() {
    return (await this.redis.del('arena:handover')) === 1;
  }
  async ping() {
    await this.redis.ping();
  }
  async close() {
    await this.redis.quit();
  }
}

/** Retry delays after a failed write: quick at first, then every few seconds until it lands. */
const RETRY_MS = [250, 500, 1000, 2000, 5000];
/** Owners hear about it when snapshots have not been saved for this long. */
const ALERT_AFTER_MS = 15_000;

/**
 * Snapshot writes never get lost to a blip (Redis restarting, a dropped connection): the
 * latest write of every room and game waits here and is retried until it lands. A newer write
 * of the same room or game replaces the waiting one, so the store always ends with the latest
 * state. Callers are never failed: the game goes on in memory while the store catches up.
 */
export class ResilientStore implements SnapshotStore {
  private readonly pending = new Map<string, () => Promise<void>>();
  private timer: NodeJS.Timeout | null = null;
  private attempt = 0;
  private failingSince: number | null = null;
  private retrying = false;

  constructor(
    private readonly inner: SnapshotStore,
    private readonly log: FastifyBaseLogger,
    private readonly alerts?: Alerts,
  ) {}

  get durable(): boolean {
    return this.inner.durable;
  }

  /** Writes still waiting to land. */
  get backlog(): number {
    return this.pending.size;
  }

  saveRoom(room: Room) {
    // Serialised now: the room object keeps changing while a retry waits.
    const copy = structuredClone(room);
    return this.write(`room:${room.id}`, () => this.inner.saveRoom(copy));
  }
  deleteRoom(id: string) {
    return this.write(`room:${id}`, () => this.inner.deleteRoom(id));
  }
  saveGame(game: GameSnapshot) {
    const copy = structuredClone(game);
    return this.write(`game:${game.gameId}`, () => this.inner.saveGame(copy));
  }
  deleteGame(id: string) {
    return this.write(`game:${id}`, () => this.inner.deleteGame(id));
  }

  private async write(key: string, op: () => Promise<void>): Promise<void> {
    this.pending.set(key, op);
    // Older writes still waiting go first: the store sees the changes in order.
    if (this.timer || this.retrying) return;
    try {
      await op();
      if (this.pending.get(key) === op) this.pending.delete(key);
      if (!this.pending.size) this.recovered();
    } catch (error) {
      this.failed(error);
    }
  }

  private failed(error: unknown): void {
    metrics.inc('arena_snapshot_failures_total', 'Snapshot writes that failed and wait for a retry');
    const now = Date.now();
    if (this.failingSince === null) {
      this.failingSince = now;
      this.log.warn({ err: error, backlog: this.pending.size }, 'snapshot write failed; retrying');
    } else if (now - this.failingSince >= ALERT_AFTER_MS) {
      this.alerts?.raise(
        'snapshots',
        `Redis не отвечает ${Math.round((now - this.failingSince) / 1000)} с: снимки игр не сохраняются (ждут ${this.pending.size}). Игры идут, но при падении сервера откатятся.`,
        { err: error },
      );
    }
    this.schedule();
  }

  private recovered(): void {
    if (this.failingSince === null) return;
    const ms = Date.now() - this.failingSince;
    this.failingSince = null;
    this.attempt = 0;
    this.log.info({ ms }, 'snapshot store recovered');
    this.alerts?.resolve('snapshots', `Redis снова работает, все снимки игр сохранены (перерыв ${Math.round(ms / 1000)} с).`);
  }

  private schedule(): void {
    if (this.timer) return;
    const delay = RETRY_MS[Math.min(this.attempt, RETRY_MS.length - 1)]!;
    this.attempt++;
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.retry();
    }, delay);
    this.timer.unref();
  }

  /** Lands the waiting writes oldest first, always the latest version of each. Throws on the first failure. */
  private async drainPending(): Promise<void> {
    while (this.pending.size) {
      const [key, op] = this.pending.entries().next().value!;
      await op();
      if (this.pending.get(key) === op) this.pending.delete(key);
    }
  }

  private async retry(): Promise<void> {
    this.retrying = true;
    try {
      await this.drainPending();
      this.recovered();
    } catch (error) {
      this.failed(error);
    } finally {
      this.retrying = false;
    }
  }

  /** Before handing the tables over: every waiting write lands, or the time is up. */
  async flush(maxMs = 5_000): Promise<boolean> {
    const deadline = Date.now() + maxMs;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.retrying = true;
    try {
      while (this.pending.size && Date.now() < deadline) {
        try {
          await this.drainPending();
        } catch {
          await new Promise((r) => setTimeout(r, 250));
        }
      }
    } finally {
      this.retrying = false;
    }
    if (this.pending.size) this.log.error({ backlog: this.pending.size }, 'snapshots not saved before shutdown');
    else this.recovered();
    return this.pending.size === 0;
  }

  loadAll() {
    return this.inner.loadAll();
  }
  acquireLease(owner: string, ttlMs: number) {
    return this.inner.acquireLease(owner, ttlMs);
  }
  renewLease(owner: string, ttlMs: number) {
    return this.inner.renewLease(owner, ttlMs);
  }
  releaseLease(owner: string) {
    return this.inner.releaseLease(owner);
  }
  /** Best effort: losing one only weakens the duplicate check across a restart. */
  async saveReply(key: string, ttlMs: number) {
    await this.inner.saveReply(key, ttlMs).catch(() => undefined);
  }
  async hasReply(key: string) {
    return this.inner.hasReply(key).catch(() => false);
  }
  markHandover() {
    return this.inner.markHandover();
  }
  takeHandover() {
    return this.inner.takeHandover();
  }
  ping() {
    return this.inner.ping();
  }
  async close() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    await this.inner.close();
  }
}
