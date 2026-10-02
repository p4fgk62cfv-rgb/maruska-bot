import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import type { RoomSettings } from '@arena/shared';
import { buildApp, type AppHandle } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { createContext } from '../src/context.js';
import { createDb, type Db } from '../src/db.js';
import { signInitData } from '../src/telegram/initData.js';
import { Bot } from './bots.js';

const url = process.env.TEST_DATABASE_URL;
const BOT_TOKEN = '123456:TEST-token-for-moderation';
const SECRET = 'internal-secret-789';
const ROOM: Omit<RoomSettings, 'password'> = {
  stake: 1000, players: 2, deckSize: 36, speed: 'fast', variant: 'podkidnoy', throwIn: 'all', fairness: 'fair', ending: 'classic', server: 'almaz', isPrivate: false,
};

interface Player {
  id: string;
  tg: number;
  token: string;
  ws: Bot;
}

describe.skipIf(!url)('integrity and moderation', () => {
  let db: Db;
  let handle: AppHandle;
  let address: string;
  const sockets: Bot[] = [];
  let nextTg = 970_000_000 + Math.floor(Math.random() * 10_000_000);

  beforeAll(async () => {
    const config = loadConfig({
      NODE_ENV: 'test', DATABASE_URL: url!, BOT_TOKEN, SESSION_SECRET: 'm'.repeat(40), WEB_DIST: '/none',
      INTERNAL_API_SECRET: SECRET, SIGNUP_BONUS_CREDITS: '20000',
    });
    db = createDb(url!);
    handle = await buildApp(createContext(config, db), { bot: null });
    address = await handle.app.listen({ port: 0, host: '127.0.0.1' });
  });

  afterAll(async () => {
    for (const s of sockets) s.close();
    await handle?.app.close();
    await db?.$disconnect();
  });

  async function player(name: string): Promise<Player> {
    const tg = nextTg++;
    const initData = signInitData({ auth_date: String(Math.floor(Date.now() / 1000)), user: JSON.stringify({ id: tg, first_name: name }) }, BOT_TOKEN);
    const res = await handle.app.inject({ method: 'POST', url: '/api/auth/telegram', payload: { initData }, remoteAddress: `10.3.${tg % 250}.${tg % 200}` });
    const { token, me } = res.json();
    const ws = new Bot(name, me.id, token, address);
    await ws.connect();
    sockets.push(ws);
    return { id: me.id, tg, token, ws };
  }

  const call = (p: Player, method: 'GET' | 'POST', path: string, payload?: object) =>
    handle.app.inject({ method, url: `/api${path}`, payload, headers: { authorization: `Bearer ${p.token}` } });
  const internal = (method: 'GET' | 'POST', path: string, payload?: object) =>
    handle.app.inject({ method, url: `/api/internal${path}`, payload, headers: { authorization: `Bearer ${SECRET}` } });

  /** `dumper` joins `receiver`'s table and gives up at once — the classic credit transfer. */
  async function dump(dumper: Player, receiver: Player): Promise<void> {
    const room = (await call(receiver, 'POST', '/rooms', ROOM)).json().room;
    await call(dumper, 'POST', `/rooms/${room.id}/join`, {});
    await receiver.ws.send({ type: 'READY', roomId: room.id, ready: true });
    await dumper.ws.send({ type: 'READY', roomId: room.id, ready: true });
    const started = await dumper.ws.waitFor((m) => m.type === 'GAME_STARTED' && m.roomId === room.id);
    if (started.type !== 'GAME_STARTED') throw new Error('unreachable');
    await dumper.ws.send({ type: 'LEAVE_GAME', gameId: started.gameId });
    await receiver.ws.waitFor((m) => m.type === 'GAME_FINISHED' && m.gameId === started.gameId);
  }

  it('flags a pair where one side keeps giving up credits to the other; honest pairs are not flagged', async () => {
    const dumper = await player('Даритель');
    const receiver = await player('Получатель');
    for (let i = 0; i < 5; i++) await dump(dumper, receiver);

    const flagged = (await internal('GET', `/integrity/suspicious?minGames=5&minCredits=1000&telegramId=${dumper.tg}`)).json();
    const pair = flagged.find((p: { loser: { id: string } }) => p.loser.id === dumper.id);
    expect(pair).toMatchObject({ winner: { id: receiver.id }, games: 5, lostToWinner: 5, gaveUp: 5, credits: 4750 });
    expect(flagged.some((p: { loser: { id: string } }) => p.loser.id === receiver.id)).toBe(false);
  }, 30_000);

  it('a ban works at once: the socket is closed, issued sessions stop working, login is refused', async () => {
    const cheat = await player('Нарушитель');
    const res = await internal('POST', '/moderation/ban', { telegramId: String(cheat.tg), days: 3, reason: 'передача кредитов' });
    expect(res.statusCode).toBe(200);
    await new Promise((r) => setTimeout(r, 100));
    expect(cheat.ws.closedWith).toBe(4001);
    expect((await call(cheat, 'GET', '/me')).json()).toMatchObject({ error: 'BANNED' });

    await internal('POST', '/moderation/unban', { telegramId: String(cheat.tg) });
    expect((await call(cheat, 'GET', '/me')).statusCode).toBe(200);
  });

  it('claws credits back once per request id and never below zero', async () => {
    const p = await player('Штраф');
    const body = { telegramId: String(p.tg), currency: 'CREDITS', amount: 5000, reason: 'сговор', requestId: `req-${p.tg}` };
    expect((await internal('POST', '/moderation/clawback', body)).json()).toEqual({ taken: 5000 });
    expect((await internal('POST', '/moderation/clawback', body)).json()).toEqual({ taken: 0 });
    expect((await internal('POST', '/moderation/clawback', { ...body, amount: 1_000_000, requestId: `req2-${p.tg}` })).json()).toEqual({ taken: 15000 });
    expect((await handle.ctx.users.wallet(p.id)).credits).toBe(0);
  });

  it('internal endpoints are closed without the secret', async () => {
    expect((await handle.app.inject({ method: 'GET', url: '/api/internal/integrity/suspicious' })).statusCode).toBe(401);
  });

  it('exposes metrics and readiness', async () => {
    const ready = await handle.app.inject({ method: 'GET', url: '/ready' });
    expect(ready.json()).toEqual({ ok: true });
    const text = (await internal('GET', '/metrics')).body;
    expect(text).toContain('arena_games_finished_total{kind="loser",reason="surrender"}');
    expect(text).toMatch(/arena_ws_online \d+/);
    expect(text).toContain('arena_event_loop_lag_p99_ms');
  });
});
