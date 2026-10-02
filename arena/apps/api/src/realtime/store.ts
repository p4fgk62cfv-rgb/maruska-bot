import { Redis } from 'ioredis';
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
  /** Survives restarts: true when this store is shared/persistent (Redis). */
  readonly durable: boolean;
  ping(): Promise<void>;
  close(): Promise<void>;
}

export class MemoryStore implements SnapshotStore {
  readonly durable = false;
  private rooms = new Map<string, Room>();
  private games = new Map<string, GameSnapshot>();

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
  async ping() {
    await this.redis.ping();
  }
  async close() {
    await this.redis.quit();
  }
}
