import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { Redis } from 'ioredis';
import { buildApp, type AppHandle } from '../src/app.js';
import { loadConfig, type Config } from '../src/config.js';
import { createContext, type BaseContext } from '../src/context.js';
import { createDb, type Db } from '../src/db.js';
import { RedisStore, type SnapshotStore } from '../src/realtime/store.js';
import { seedCatalog } from '../src/services/catalog.js';
import { signInitData } from '../src/telegram/initData.js';
import { Bot } from './bots.js';
import { parseRoomStartParam, type RoomSettings } from '@arena/shared';

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
    config = loadConfig({ NODE_ENV: 'test', DATABASE_URL: url!, BOT_TOKEN, SESSION_SECRET: 'm'.repeat(40), WEB_DIST: '/none', RAKE_PERCENT: '5', INTERNAL_API_SECRET: 'internal-secret-multi-123', AUTH_RATE_LIMIT: '100' });
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
    await watcher.send({ type: 'LOBBY_SUBSCRIBE', filter: { scope: 'open', stakes: [100], players: [], deckSizes: [], speeds: [], modes: ['podkidnoy'] } });

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

    // The same company stays at the table: it waits again, and the next deal starts when both are ready.
    for (const p of players) p.autoplay = false;
    await p1.waitFor((m) => m.type === 'ROOM_UPDATED' && m.room.id === roomId && m.room.status === 'waiting');
    const room = handle.ctx.realtime.rooms.get(roomId)!;
    expect(room.seats.map((s) => s.userId).sort()).toEqual([p1.userId, p2.userId].sort());
    expect(room.seats.every((s) => !s.ready)).toBe(true);
    expect(room.readyDeadline).not.toBeNull();
    // The autoplaying bots spent their message budget; let the per-socket limiter refill.
    await new Promise((resolve) => setTimeout(resolve, 2100));
    // Smiles work between deals too.
    expect((await p1.send({ type: 'ROOM_EMOJI', roomId, emoji: '😘' })).type).toBe('ACK');
    await p2.waitFor((m) => m.type === 'EMOJI' && m.userId === p1.userId && m.emoji === '😘');
    // A picture sticker needs its pack: P2 has not bought «Панда».
    await new Promise((resolve) => setTimeout(resolve, 1600));
    expect(await p2.send({ type: 'ROOM_EMOJI', roomId, emoji: 'panda:03' })).toMatchObject({ type: 'ERROR', code: 'FORBIDDEN' });
    for (const p of players) expect((await p.send({ type: 'READY', roomId, ready: true })).type).toBe('ACK');
    const again = await p1.waitFor((m) => m.type === 'GAME_STARTED' && m.gameId !== gameId);
    expect(room.status).toBe('playing');
    await handle.ctx.realtime.games.abort((again as { gameId: string }).gameId);
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

  /** Test-only access to the runner's snapshot and timer. */
  const internals = (gameId: string) => handle.ctx.realtime.games.get(gameId) as unknown as {
    snap: { state: { turnDeadline: number | null; attacker: string; version: number }; reserve?: Record<string, number>; grace?: unknown };
    schedule(): void;
  };
  /** Makes the current turn run out right now. */
  const expire = (gameId: string) => {
    const r = internals(gameId);
    r.snap.state = { ...r.snap.state, turnDeadline: Date.now() };
    r.schedule();
  };
  const token = (bot: Bot) => (bot as unknown as { authToken: string }).authToken;

  it('lost connection on your turn: the table waits, the player comes back; a long absence loses the game', async () => {
    const { players, roomId } = await table(2);
    const gameId = await startGame(players, roomId);
    const mover = players.find((p) => p.userId === internals(gameId).snap.state.attacker)!;
    const other = players.find((p) => p !== mover)!;
    await other.waitFor((m) => m.type === 'GAME_STATE');

    // Offline: the opponent sees it at once.
    other.inbox = [];
    mover.close();
    await other.waitFor((m) => m.type === 'GAME_STATE' && m.players.some((p) => p.userId === mover.userId && !p.connected));

    // The turn runs out while offline: no loss, the table waits on the reconnect reserve.
    expire(gameId);
    const waiting = await other.waitFor((m) => m.type === 'GAME_STATE' && m.waiting?.userId === mover.userId);
    const until = (waiting as { waiting: { until: number } }).waiting.until;
    expect(until - Date.now()).toBeGreaterThan(50_000);
    expect(handle.ctx.realtime.games.get(gameId)!.state.status).toBe('playing');

    // Back: same game, the wait is over, a few seconds to look around, the reserve is partly spent.
    await new Promise((r) => setTimeout(r, 300));
    mover.inbox = [];
    other.inbox = [];
    await mover.connect(token(mover));
    const back = await mover.waitFor((m) => m.type === 'GAME_STATE');
    expect((back as { waiting: unknown }).waiting).toBeNull();
    expect((back as { state: { gameId: string } }).state.gameId).toBe(gameId);
    expect(internals(gameId).snap.state.turnDeadline! - Date.now()).toBeGreaterThan(8_000);
    const reserve = internals(gameId).snap.reserve![mover.userId]!;
    expect(reserve).toBeLessThan(60_000);
    expect(reserve).toBeGreaterThan(55_000);
    await other.waitFor((m) => m.type === 'GAME_STATE' && m.players.every((p) => p.connected));

    // Gone again with the reserve used up: the next timeout loses the game and the stakes settle.
    mover.close();
    await other.waitFor((m) => m.type === 'GAME_STATE' && m.players.some((p) => p.userId === mover.userId && !p.connected));
    internals(gameId).snap.reserve = { [mover.userId]: 500 };
    expire(gameId);
    await other.waitFor((m) => m.type === 'GAME_FINISHED');
    expect(other.result!.reason).toBe('timeout');
    expect(other.result!.loserId).toBe(mover.userId);
    const game = await db.game.findUniqueOrThrow({ where: { id: gameId } });
    expect(game.status).toBe('FINISHED');
  }, 30_000);

  it('a move resent after a reconnect (same request id, new socket) is applied once', async () => {
    const { players, roomId } = await table(2);
    const gameId = await startGame(players, roomId);
    const mover = players.find((p) => p.userId === internals(gameId).snap.state.attacker)!;
    const state = (await mover.waitFor((m) => m.type === 'GAME_STATE')) as { state: { you: { hand: string[] } } };
    const card = state.state.you.hand[0]!;
    const frame = JSON.stringify({ type: 'PLAY_CARD', gameId, card, rid: 'page1234:7' });
    const ack = (bot: Bot) => bot.waitFor((m) => m.type === 'ACK' && m.rid === 'page1234:7');

    mover.ws.send(frame);
    await ack(mover);
    const version = internals(gameId).snap.state.version;

    // The answer was «lost»: the app reconnects and sends the very same request again.
    mover.close();
    mover.inbox = [];
    await mover.connect(token(mover));
    mover.ws.send(frame);
    await ack(mover);
    expect(internals(gameId).snap.state.version).toBe(version);

    // Two copies at once (double tap): one is applied, both are answered.
    const v2 = internals(gameId).snap.state.version;
    const other = players.find((p) => p !== mover)!;
    await other.waitFor((m) => m.type === 'GAME_STATE' && m.state.version === v2);
    const take = JSON.stringify({ type: 'TAKE_CARDS', gameId, rid: 'page5678:1' });
    other.ws.send(take);
    other.ws.send(take);
    await other.waitFor((m) => m.type === 'ACK' && m.rid === 'page5678:1');
    await new Promise((r) => setTimeout(r, 200));
    expect(other.inbox.filter((m) => m.type === 'ACK' && m.rid === 'page5678:1')).toHaveLength(2);
    expect(other.inbox.filter((m) => m.type === 'ERROR')).toHaveLength(0);
    expect(internals(gameId).snap.state.version).toBe(v2 + 1);
  }, 30_000);

  it('bots fill an empty public table, play a whole game for credits, and leave with the people', async () => {
    await handle.ctx.bots.setSettings({ enabled: true, delaySec: 1, level: 'hard' });
    try {
      const human = await player('Solo', 10);
      const created = (await api(human, 'POST', '/rooms', { ...SETTINGS, players: 2 })).json();
      const roomId: string = created.room.id;
      const before = (await api(human, 'GET', '/me')).json();

      // A private table never gets bots.
      const friendHost = await player('PrivateHost', 10);
      const privateRoom = (await api(friendHost, 'POST', '/rooms', { ...SETTINGS, players: 2, isPrivate: true, password: '1234' })).json().room.id;

      // Nobody comes in → a bot takes the seat, already ready.
      const joined = await human.waitFor((m) => m.type === 'ROOM_UPDATED' && m.room.id === roomId && m.room.seats.some((x) => x.bot), 5000);
      const seats = (joined as { room: { seats: { bot?: boolean; ready: boolean }[] } }).room.seats;
      expect(seats.filter((x) => x.bot)).toHaveLength(1);
      expect(seats.find((x) => x.bot)!.ready).toBe(true);
      expect(handle.ctx.realtime.rooms.get(privateRoom)!.seats).toHaveLength(1);

      expect((await human.send({ type: 'READY', roomId, ready: true })).type).toBe('ACK');
      const started = await human.waitFor((m) => m.type === 'GAME_STARTED');
      const gameId = (started as { gameId: string }).gameId;
      expect((started as { players: { bot?: boolean }[] }).players.some((x) => x.bot)).toBe(true);

      // The person plays; the bot answers on its own.
      expect((await human.send({ type: 'USE_FEATURE', gameId, feature: 'hints' })).type).toBe('ACK');
      human.autoplay = true;
      await human.send({ type: 'RECONNECT', roomId });
      await human.waitFor((m) => m.type === 'GAME_FINISHED', 90_000);
      const result = human.result!;
      expect(result.reason).not.toBe('timeout');

      // Credits moved like in any game; rating stayed.
      const after = (await api(human, 'GET', '/me')).json();
      const mine = result.payouts.find((p) => p.userId === human.userId)!;
      expect(after.rating).toBe(before.rating);
      expect(mine.ratingGain).toBe(0);
      expect(after.wallet.credits - before.wallet.credits).toBe(mine.net);

      // The person leaves the table → the bot leaves too and the table closes.
      await new Promise((r) => setTimeout(r, 300));
      expect((await api(human, 'POST', `/rooms/${roomId}/leave`)).statusCode).toBe(200);
      expect(handle.ctx.realtime.rooms.get(roomId)).toBeUndefined();

      // Bots are not in the leaderboard and cannot be friended.
      const board = (await api(human, 'GET', '/leaderboard?by=rating')).json() as { id: string }[];
      const botId = result.payouts.find((p) => p.userId !== human.userId)!.userId;
      expect(board.some((r) => r.id === botId)).toBe(false);
      expect((await api(human, 'POST', '/friends/requests', { userId: botId })).json().error).toBe('NOT_FOUND');
    } finally {
      await handle.ctx.bots.setSettings({ enabled: false, delaySec: 12, level: 'normal' });
    }
  }, 120_000);

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
    // Listed on the «Приватные» tab only; the listing never carries the password.
    const privateList = (await api(guest, 'GET', `/rooms?scope=private`)).json() as { id: string }[];
    expect(privateList.some((r) => r.id === roomId)).toBe(true);
    expect(JSON.stringify(privateList)).not.toContain('secret');
    expect((await api(guest, 'POST', `/rooms/${roomId}/join`, {})).json()).toMatchObject({ error: 'WRONG_PASSWORD' });
    expect((await api(guest, 'POST', `/rooms/${roomId}/join`, { password: 'nope' })).json()).toMatchObject({ error: 'WRONG_PASSWORD' });
    expect((await api(guest, 'POST', `/rooms/${roomId}/join`, { invite: code })).statusCode).toBe(200);
    expect((await api(guest, 'GET', `/rooms?stakes=100`)).json().some((r: { id: string }) => r.id === roomId)).toBe(false);

    const intruder = new Bot('X', 'x', 'bad.token', address);
    await intruder.connect('bad.token');
    await new Promise((r) => setTimeout(r, 200));
    expect(intruder.closedWith).toBe(4001);
  });

  it('a moderator cancels a running game: stakes come back, players see «cancelled»', async () => {
    const { players, roomId } = await table(2);
    const gameId = await startGame(players, roomId);
    for (const p of players) expect((await base.users.wallet(p.userId)).credits).toBe(1350);
    const res = await handle.app.inject({ method: 'POST', url: `/api/internal/admin/games/${gameId}/abort`, headers: { authorization: 'Bearer internal-secret-multi-123' } });
    expect(res.json()).toEqual({ ok: true });
    for (const p of players) {
      const done = (await p.waitFor((m) => m.type === 'GAME_FINISHED')) as { result: { reason: string } };
      expect(done.result.reason).toBe('cancelled');
      expect((await base.users.wallet(p.userId)).credits).toBe(1450);
    }
    expect((await db.game.findUniqueOrThrow({ where: { id: gameId } })).status).toBe('ABORTED');
  });

  it('«Быстрая игра» seats two players at one table', async () => {
    const a = await player('QuickA');
    const b = await player('QuickB');
    const ra = (await api(a, 'POST', '/rooms/quick', { stake: 1000 })).json();
    const rb = (await api(b, 'POST', '/rooms/quick', { stake: 1000 })).json();
    expect(rb.room.id).toBe(ra.room.id);
    expect(rb.room.seats).toHaveLength(2);
  });

  it('a second instance (rolling deploy) leaves live games alone and refunds only abandoned ones', async () => {
    const { players, roomId } = await table(2);
    const gameId = await startGame(players, roomId);
    const other = await buildApp(base, { bot: null });
    try {
      await other.ctx.realtime.sweepOrphans();
      expect((await db.game.findUniqueOrThrow({ where: { id: gameId } })).status).toBe('PLAYING');

      // Three minutes of silence: the game is treated as abandoned and the stakes come back.
      await other.ctx.realtime.sweepOrphans(Date.now() + 180_000);
      expect((await db.game.findUniqueOrThrow({ where: { id: gameId } })).status).toBe('ABORTED');
      for (const p of players) expect((await base.users.wallet(p.userId)).credits).toBe(1450);
    } finally {
      await other.app.close();
    }
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

  it.skipIf(!redisUrl)('a table whose game was lost in a restart is freed, and the stakes come back', async () => {
    const redis = new Redis(redisUrl!);
    await redis.flushdb();
    await handle.app.close();
    await start(new RedisStore(redisUrl!));

    const { players, roomId } = await table(2);
    const gameId = await startGame(players, roomId);
    await players[0]!.waitFor((m) => m.type === 'GAME_STATE');
    for (const p of players) p.close();
    await handle.app.close();
    // The game snapshot is gone (expired, lost), the room snapshot still says «playing».
    await redis.del(`arena:game:${gameId}`);
    await redis.quit();
    await start(new RedisStore(redisUrl!));

    await new Promise((r) => setTimeout(r, 50));
    const room = handle.ctx.realtime.rooms.get(roomId)!;
    expect(room.status).toBe('waiting');
    expect(room.gameId).toBeNull();
    // Nobody is stuck: a player can leave the table and sit elsewhere.
    expect((await api(players[0]!, 'POST', `/rooms/${roomId}/leave`)).statusCode).toBe(200);

    // The orphaned game is refunded once it has been quiet long enough.
    await handle.ctx.realtime.sweepOrphans(Date.now() + 10 * 60_000);
    expect((await db.game.findUniqueOrThrow({ where: { id: gameId } })).status).toBe('ABORTED');
    const refunds = await db.transaction.count({ where: { source: `game:${gameId}`, type: 'GAME_REFUND' } });
    expect(refunds).toBe(2);
  }, 30_000);

  it('one table at a time: two joins at once seat the player only once', async () => {
    const hosts = [await player('H1', 10), await player('H2', 10)];
    const rooms = [];
    for (const h of hosts) rooms.push((await api(h, 'POST', '/rooms', { ...SETTINGS, players: 3 })).json().room.id as string);
    const guest = await player('Guest', 10);
    const results = await Promise.all(rooms.map((id) => api(guest, 'POST', `/rooms/${id}/join`, {})));
    expect(results.every((r) => r.statusCode === 200)).toBe(true);
    const seatedIn = rooms.filter((id) => handle.ctx.realtime.rooms.get(id)!.seats.some((s) => s.userId === guest.userId));
    expect(seatedIn).toHaveLength(1);
    // And «create» racing «quick» ends with one table too.
    const racer = await player('Racer', 10);
    await Promise.all([api(racer, 'POST', '/rooms', { ...SETTINGS, players: 4 }), api(racer, 'POST', '/rooms/quick', {})]);
    const tables = handle.ctx.realtime.rooms.list().filter((r) => r.seats.some((s) => s.userId === racer.userId));
    expect(tables).toHaveLength(1);
  });

  it('a private table stops taking PIN guesses after a series of wrong ones; the invite link still works', async () => {
    const host = await player('Pin', 10);
    const created = (await api(host, 'POST', '/rooms', { ...SETTINGS, players: 3, isPrivate: true, password: '4321' })).json();
    const roomId: string = created.room.id;
    const guesser = await player('Guesser', 10);
    for (let i = 0; i < 8; i++) {
      const res = await api(guesser, 'POST', `/rooms/${roomId}/join`, { password: String(1000 + i) });
      expect(res.json().error, res.body).toBe('WRONG_PASSWORD');
    }
    // Even the right PIN is refused now…
    expect((await api(guesser, 'POST', `/rooms/${roomId}/join`, { password: '4321' })).json().error).toBe('RATE_LIMITED');
    // …but a friend with the invite link gets in.
    const invite = parseRoomStartParam(new URL(created.invite.link).searchParams.get('startapp'))!.invite!;
    const friend = await player('Friend', 10);
    expect((await api(friend, 'POST', `/rooms/${roomId}/join`, { invite })).statusCode).toBe(200);
  });
});
