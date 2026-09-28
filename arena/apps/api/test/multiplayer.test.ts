import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import type { FastifyInstance } from 'fastify';
import { Redis } from 'ioredis';
import { buildApp, type AppHandle } from '../src/app.js';
import { loadConfig, type Config } from '../src/config.js';
import { createContext, type BaseContext } from '../src/context.js';
import { createDb, type Db } from '../src/db.js';
import { RedisStore, type SnapshotStore } from '../src/realtime/store.js';
import { seedCatalog } from '../src/services/catalog.js';
import { signInitData } from '../src/telegram/initData.js';
import { Bot } from './bots.js';
import type { RoomSettings } from '@arena/shared';

const url = process.env.TEST_DATABASE_URL;
const redisUrl = process.env.TEST_REDIS_URL;
const BOT_TOKEN = '123456:TEST-token-for-multiplayer';

const SETTINGS: Omit<RoomSettings, 'password'> = {
  stake: 100,
  players: 2,
  deckSize: 36,
  speed: 'fast',
  variant: 'podkidnoy',
  throwIn: 'all',
  fairness: 'fair',
  ending: 'classic',
  server: 'almaz',
  isPrivate: false,
};

describe.skipIf(!url)('real-time multiplayer over WebSocket', () => {
  let db: Db;
  let config: Config;
  let base: BaseContext;
  let handle: AppHandle;
  let address: string;
  const bots: Bot[] = [];
  let nextTg = 800_000_000 + Math.floor(Math.random() * 10_000_000);

  async function start(store?: SnapshotStore): Promise<void> {
    handle = await buildApp(base, { store, bot: null });
    address = await handle.app.listen({ port: 0, host: '127.0.0.1' });
  }

  beforeAll(async () => {
    config = loadConfig({ NODE_ENV: 'test', DATABASE_URL: url!, BOT_TOKEN, SESSION_SECRET: 'm'.repeat(40), WEB_DIST: '/none', RAKE_PERCENT: '5' });
    db = createDb(url!);
    await seedCatalog(db);
    base = createContext(config, db);
    await start();
  });

  afterEach(() => {
    for (const b of bots.splice(0)) b.close();
  });

  afterAll(async () => {
    await handle?.app.close();
    await db?.$disconnect();
  });

  async function player(name: string, coins = 0): Promise<Bot> {
    const id = nextTg++;
    const initData = signInitData(
      { auth_date: String(Math.floor(Date.now() / 1000)), user: JSON.stringify({ id, first_name: name }) },
      BOT_TOKEN,
    );
    const res = await handle.app.inject({ method: 'POST', url: '/api/auth/telegram', payload: { initData } });
    const { token, me } = res.json();
    if (coins) {
      await base.ledger.post({ userId: me.id, currency: 'COINS', amount: BigInt(coins), type: 'ADMIN', source: 'test', idempotencyKey: `coins:${me.id}` });
    }
    const bot = new Bot(name, me.id, token, address);
    (bot as unknown as { authToken: string }).authToken = token;
    await bot.connect();
    bots.push(bot);
    return bot;
  }

  const api = (bot: Bot, method: 'GET' | 'POST', path: string, payload?: object) =>
    handle.app.inject({ method, url: `/api${path}`, payload, headers: { authorization: `Bearer ${(bot as unknown as { authToken: string }).authToken}` } });

  async function table(n: number, settings: Partial<typeof SETTINGS> = {}): Promise<{ players: Bot[]; roomId: string }> {
    const players: Bot[] = [];
    for (let i = 0; i < n; i++) players.push(await player(`P${i + 1}`, 10));
    const created = await api(players[0]!, 'POST', '/rooms', { ...SETTINGS, players: n, ...settings });
    expect(created.statusCode).toBe(200);
    const roomId: string = created.json().room.id;
    for (const p of players.slice(1)) expect((await api(p, 'POST', `/rooms/${roomId}/join`, {})).statusCode).toBe(200);
    return { players, roomId };
  }

  async function startGame(players: Bot[], roomId: string): Promise<string> {
    for (const p of players) expect((await p.send({ type: 'READY', roomId, ready: true })).type).toBe('ACK');
    const started = await players[0]!.waitFor((m) => m.type === 'GAME_STARTED');
    return (started as { gameId: string }).gameId;
  }

  async function playOut(players: Bot[], gameId: string): Promise<void> {
    for (const p of players) {
      expect((await p.send({ type: 'USE_FEATURE', gameId, feature: 'hints' })).type).toBe('ACK');
    }
    for (const p of players) {
      p.autoplay = true;
      await p.send({ type: 'RECONNECT', roomId: handle.ctx.realtime.games.get(gameId)!.roomId });
    }
    await Promise.all(players.map((p) => p.waitFor((m) => m.type === 'GAME_FINISHED', 60_000)));
    // Bots always have a legal move, so the game must end on the cards, not on a turn timer.
    expect(players[0]!.result!.reason).not.toBe('timeout');
  }

  it('two players: lobby → room → ready → a full game → payouts, rating and history', async () => {
    const watcher = await player('Watcher');
    await watcher.send({ type: 'LOBBY_SUBSCRIBE', filter: { stakes: [100], players: [], deckSizes: [], speeds: [], modes: ['podkidnoy'] } });

    const { players, roomId } = await table(2);
    await watcher.waitFor((m) => m.type === 'ROOM_CREATED' && m.room.id === roomId);
    // Full room disappears from the lobby.
    await watcher.waitFor((m) => m.type === 'ROOM_REMOVED' && m.roomId === roomId);

    const gameId = await startGame(players, roomId);
    const [p1, p2] = players as [Bot, Bot];
    for (const p of players) expect((await base.users.wallet(p.userId)).credits).toBe(1350);

    // Hidden information never leaves the server.
    const truth = handle.ctx.realtime.games.get(gameId)!.state;
    await p1.waitFor((m) => m.type === 'GAME_STATE');
    const p1Json = JSON.stringify(p1.latest('GAME_STATE'));
    for (const card of truth.players.find((p) => p.id === p2.userId)!.hand) expect(p1Json).not.toContain(`"${card}"`);
    for (const card of truth.deck.slice(0, -1)) expect(p1Json).not.toContain(`"${card}"`);

    await playOut(players, gameId);
    const result = p1.result!;
    const total = result.payouts.reduce((s, p) => s + p.net, 0);
    if (result.kind === 'loser') {
      expect(result.payouts.find((p) => p.userId === result.loserId)!.net).toBe(-100);
      expect(total).toBe(-5);
      const winner = result.payouts.find((p) => p.userId !== result.loserId)!;
      expect(winner.ratingGain).toBeGreaterThan(0);
      expect(winner.bonusMultiplier).toBe(2);
    } else {
      expect(total).toBe(0);
    }
    const credits = await Promise.all(players.map((p) => base.users.wallet(p.userId)));
    expect(credits.reduce((s, w) => s + w.credits, 0)).toBe(2900 + total);

    const game = await db.game.findUniqueOrThrow({ where: { id: gameId }, include: { result: true, _count: { select: { moves: true } } } });
    expect(game.status).toBe('FINISHED');
    expect(game.result).not.toBeNull();
    expect(game._count.moves).toBeGreaterThan(5);
    const profile = await db.profile.findUniqueOrThrow({ where: { userId: p1.userId } });
    expect(profile.gamesPlayed).toBe(1);
    const firstGame = await db.userAchievement.findFirst({ where: { userId: p1.userId, achievement: { key: 'first_game' } } });
    expect(firstGame?.unlockedAt).not.toBeNull();
    expect(handle.ctx.realtime.rooms.get(roomId)).toBeUndefined();
  }, 90_000);

  it('three players: a dropped player reconnects to the same game and it plays to the end', async () => {
    const { players, roomId } = await table(3, { variant: 'perevodnoy', throwIn: 'neighbors' });
    const gameId = await startGame(players, roomId);
    const [p1, p2, p3] = players as [Bot, Bot, Bot];
    await p2.waitFor((m) => m.type === 'GAME_STATE');

    p2.close();
    await p1.waitFor((m) => m.type === 'PLAYER_DISCONNECTED' && m.userId === p2.userId);
    const version = handle.ctx.realtime.games.get(gameId)!.state.version;

    p2.inbox = [];
    await p2.connect((p2 as unknown as { authToken: string }).authToken);
    const state = await p2.waitFor((m) => m.type === 'GAME_STATE');
    expect((state as { state: { version: number } }).state.version).toBe(version);
    await p3.waitFor((m) => m.type === 'PLAYER_RECONNECTED' && m.userId === p2.userId);

    await playOut(players, gameId);
    expect(p1.result).not.toBeNull();
  }, 90_000);

  it('rejects cheating and foreign actions, and «Сдаться» is a loss', async () => {
    const { players, roomId } = await table(2);
    const gameId = await startGame(players, roomId);
    const [p1, p2] = players as [Bot, Bot];
    await p1.waitFor((m) => m.type === 'GAME_STATE');
    const truth = handle.ctx.realtime.games.get(gameId)!.state;
    const foreignCard = truth.players.find((p) => p.id === p2.userId)!.hand[0]!;

    const attacker = players.find((p) => p.userId === truth.attacker)!;
    const reply = await attacker.send({ type: 'PLAY_CARD', gameId, card: attacker === p1 ? foreignCard : truth.players.find((p) => p.id === p1.userId)!.hand[0]! });
    expect(reply).toMatchObject({ type: 'ERROR', code: 'CARD_NOT_IN_HAND' });

    const outsider = await player('Outsider');
    expect(await outsider.send({ type: 'PASS', gameId })).toMatchObject({ type: 'ERROR', code: 'NOT_FOUND' });
    expect((await api(outsider, 'POST', `/rooms/${roomId}/join`, {})).json()).toMatchObject({ error: 'GAME_ALREADY_STARTED' });

    await p2.send({ type: 'LEAVE_GAME', gameId });
    await p1.waitFor((m) => m.type === 'GAME_FINISHED');
    expect(p1.result).toMatchObject({ kind: 'loser', reason: 'surrender', loserId: p2.userId, winnerId: p1.userId });
  }, 30_000);

  it('private rooms need the password or the invite link; bad tokens are refused', async () => {
    const owner = await player('Owner');
    const created = (await api(owner, 'POST', '/rooms', { ...SETTINGS, isPrivate: true, password: 'secret' })).json();
    const roomId = created.room.id;
    const code = /game_[A-Z0-9]{8}_([A-Za-z0-9_-]+)/.exec(created.invite.link)![1]!;

    const guest = await player('Guest');
    expect((await api(guest, 'POST', `/rooms/${roomId}/join`, {})).json()).toMatchObject({ error: 'WRONG_PASSWORD' });
    expect((await api(guest, 'POST', `/rooms/${roomId}/join`, { password: 'nope' })).json()).toMatchObject({ error: 'WRONG_PASSWORD' });
    expect((await api(guest, 'POST', `/rooms/${roomId}/join`, { invite: code })).statusCode).toBe(200);
    expect((await api(guest, 'GET', `/rooms?stakes=100`)).json().some((r: { id: string }) => r.id === roomId)).toBe(false);

    const intruder = new Bot('X', 'x', 'bad.token', address);
    await intruder.connect('bad.token');
    await new Promise((r) => setTimeout(r, 200));
    expect(intruder.closedWith).toBe(4001);
  });

  it('«Быстрая игра» seats two players at one table', async () => {
    const a = await player('QuickA');
    const b = await player('QuickB');
    const ra = (await api(a, 'POST', '/rooms/quick', { stake: 1000 })).json();
    const rb = (await api(b, 'POST', '/rooms/quick', { stake: 1000 })).json();
    expect(rb.room.id).toBe(ra.room.id);
    expect(rb.room.seats).toHaveLength(2);
  });

  it.skipIf(!redisUrl)('a running game survives a server restart through Redis', async () => {
    const redis = new Redis(redisUrl!);
    await redis.flushdb();
    await redis.quit();
    await handle.app.close();
    await start(new RedisStore(redisUrl!));

    const { players, roomId } = await table(2);
    const gameId = await startGame(players, roomId);
    await players[0]!.waitFor((m) => m.type === 'GAME_STATE');
    const version = handle.ctx.realtime.games.get(gameId)!.state.version;

    for (const p of players) p.close();
    await handle.app.close();
    await start(new RedisStore(redisUrl!));
    expect(handle.ctx.realtime.games.get(gameId)?.state.version).toBe(version);

    for (const p of players) {
      p.inbox = [];
      (p as unknown as { base: string }).base = address;
      await p.connect((p as unknown as { authToken: string }).authToken);
    }
    await playOut(players, gameId);
    expect(players[0]!.result).not.toBeNull();
  }, 90_000);
});
