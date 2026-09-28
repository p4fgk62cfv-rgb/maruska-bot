import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { buildApp, type AppHandle } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { createContext } from '../src/context.js';
import { createDb, type Db } from '../src/db.js';
import { seedCatalog } from '../src/services/catalog.js';
import { signInitData } from '../src/telegram/initData.js';
import { Bot } from './bots.js';

const url = process.env.TEST_DATABASE_URL;
const BOT_TOKEN = '123456:TEST-token-for-tournaments';

interface Player {
  id: string;
  token: string;
  ws: Bot;
}

describe.skipIf(!url)('tournaments', () => {
  let db: Db;
  let handle: AppHandle;
  let address: string;
  const sockets: Bot[] = [];
  let nextTg = 950_000_000 + Math.floor(Math.random() * 10_000_000);

  beforeAll(async () => {
    const config = loadConfig({
      NODE_ENV: 'test', DATABASE_URL: url!, BOT_TOKEN, SESSION_SECRET: 't'.repeat(40), WEB_DIST: '/none',
      INTERNAL_API_SECRET: 'internal-secret-456', MATCH_READY_SECONDS: '1', SIGNUP_BONUS_CREDITS: '1000',
    });
    db = createDb(url!);
    await seedCatalog(db);
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
    const res = await handle.app.inject({ method: 'POST', url: '/api/auth/telegram', payload: { initData }, remoteAddress: `10.2.${tg % 250}.${tg % 200}` });
    const { token, me } = res.json();
    const ws = new Bot(name, me.id, token, address);
    await ws.connect();
    sockets.push(ws);
    return { id: me.id, token, ws };
  }

  const call = (p: Player, method: 'GET' | 'POST', path: string) =>
    handle.app.inject({ method, url: `/api${path}`, headers: { authorization: `Bearer ${p.token}` } });

  async function create(maxPlayers: number, entryFee: number, startsIn = -1000): Promise<string> {
    const res = await handle.app.inject({
      method: 'POST',
      url: '/api/internal/tournaments',
      headers: { authorization: 'Bearer internal-secret-456' },
      payload: { title: 'Кубок Маруськи', entryFee, maxPlayers, startsAt: new Date(Date.now() + startsIn).toISOString(), settings: { speed: 'fast' } },
    });
    expect(res.statusCode).toBe(200);
    return res.json().id;
  }

  const credits = async (p: Player) => (await handle.ctx.users.wallet(p.id)).credits;
  const settle = () => new Promise((r) => setTimeout(r, 150));

  /** Both players of the current match press «Готов», then `loser` gives up the game. */
  async function playMatch(a: Player, b: Player, loser: Player): Promise<void> {
    const roomOf = (p: Player) => p.ws.latest('TOURNAMENT_MATCH')?.roomId;
    await a.ws.waitFor((m) => m.type === 'TOURNAMENT_MATCH' && m.roomId === roomOf(a));
    const roomId = roomOf(a)!;
    expect(roomOf(b)).toBe(roomId);
    for (const p of [a, b]) expect((await p.ws.send({ type: 'READY', roomId, ready: true })).type).toBe('ACK');
    const started = await loser.ws.waitFor((m) => m.type === 'GAME_STARTED' && m.roomId === roomId);
    if (started.type !== 'GAME_STARTED') throw new Error('unreachable');
    await loser.ws.send({ type: 'LEAVE_GAME', gameId: started.gameId });
    await loser.ws.waitFor((m) => m.type === 'GAME_FINISHED' && m.gameId === started.gameId);
    await settle();
  }

  it('four players: fees in, bracket, two rounds, prizes out', async () => {
    const id = await create(4, 100, 60_000);
    const [p1, p2, p3, p4] = await Promise.all(['Аня', 'Боря', 'Вика', 'Гоша'].map(player)) as [Player, Player, Player, Player];
    for (const p of [p1, p2, p3, p4]) expect((await call(p, 'POST', `/tournaments/${id}/register`)).statusCode).toBe(200);
    expect(await credits(p1)).toBe(900);

    // Leaving before the start refunds the fee; joining again charges it again.
    await call(p4, 'POST', `/tournaments/${id}/unregister`);
    expect(await credits(p4)).toBe(1000);
    await call(p4, 'POST', `/tournaments/${id}/register`);
    const late = await player('Опоздавший');
    expect((await call(late, 'POST', `/tournaments/${id}/register`)).json()).toMatchObject({ error: 'ROOM_FULL' });
    expect((await call(p1, 'GET', `/tournaments/${id}`)).json()).toMatchObject({ prizePool: 400, players: 4, joined: true, prizes: [200, 120, 40, 40] });

    await handle.ctx.tournaments.tick(new Date(Date.now() + 120_000));
    await settle();
    let detail = (await call(p1, 'GET', `/tournaments/${id}`)).json();
    expect(detail.status).toBe('RUNNING');
    const round1 = detail.matches.filter((m: { round: number }) => m.round === 1);
    expect(round1).toHaveLength(2);

    const byId = new Map([p1, p2, p3, p4].map((p) => [p.id, p]));
    for (const m of round1) {
      const a = byId.get(m.a.id)!;
      const b = byId.get(m.b.id)!;
      await playMatch(a, b, b); // player A always wins
    }
    detail = (await call(p1, 'GET', `/tournaments/${id}`)).json();
    const final = detail.matches.find((m: { round: number }) => m.round === 2);
    expect(final).toBeDefined();
    const champ = byId.get(final.a.id)!;
    const second = byId.get(final.b.id)!;
    await playMatch(champ, second, second);

    detail = (await call(p1, 'GET', `/tournaments/${id}`)).json();
    expect(detail.status).toBe('FINISHED');
    expect(detail.entrants.map((e: { place: number }) => e.place)).toEqual([1, 2, 3, 3]);
    expect(await credits(champ)).toBe(900 + 200);
    expect(await credits(second)).toBe(900 + 120);
    const all = await Promise.all([p1, p2, p3, p4].map(credits));
    expect(all.reduce((a, b) => a + b, 0)).toBe(4000);
  }, 60_000);

  it('a player who does not press «Готов» loses; three players means one bye', async () => {
    const id = await create(4, 0);
    const players = await Promise.all(['Дима', 'Ева', 'Женя'].map(player));
    for (const p of players) await call(p, 'POST', `/tournaments/${id}/register`);
    await handle.ctx.tournaments.tick();
    await settle();
    const detail = (await call(players[0]!, 'GET', `/tournaments/${id}`)).json();
    const bye = detail.matches.find((m: { b: unknown }) => m.b === null);
    const real = detail.matches.find((m: { b: unknown }) => m.b !== null);
    expect(bye).toMatchObject({ status: 'DONE', decidedBy: 'bye' });

    const a = players.find((p) => p.id === real.a.id)!;
    const b = players.find((p) => p.id === real.b.id)!;
    await b.ws.waitFor((m) => m.type === 'TOURNAMENT_MATCH');
    const roomId = b.ws.latest('TOURNAMENT_MATCH')!.roomId;
    await b.ws.send({ type: 'READY', roomId, ready: true });
    await new Promise((r) => setTimeout(r, 1400));
    const after = (await call(a, 'GET', `/tournaments/${id}`)).json();
    expect(after.matches.find((m: { id: string }) => m.id === real.id)).toMatchObject({ winnerId: b.id, decidedBy: 'no_show' });
    // The final is already set up between the bye winner and B.
    expect(after.matches.find((m: { round: number }) => m.round === 2)).toBeDefined();
  }, 30_000);

  it('walking out of a match hands it to the opponent', async () => {
    const id = await create(4, 0);
    const [a, b] = await Promise.all(['Зина', 'Илья'].map(player)) as [Player, Player];
    for (const p of [a, b]) await call(p, 'POST', `/tournaments/${id}/register`);
    await handle.ctx.tournaments.tick();
    await a.ws.waitFor((m) => m.type === 'TOURNAMENT_MATCH');
    const roomId = a.ws.latest('TOURNAMENT_MATCH')!.roomId;
    await call(a, 'POST', `/rooms/${roomId}/leave`);
    await settle();
    const detail = (await call(b, 'GET', `/tournaments/${id}`)).json();
    expect(detail.status).toBe('FINISHED');
    expect(detail.entrants[0]).toMatchObject({ id: b.id, place: 1 });
  });

  it('fewer than two players: cancelled and fees refunded', async () => {
    const id = await create(8, 250);
    const solo = await player('Одиночка');
    await call(solo, 'POST', `/tournaments/${id}/register`);
    expect(await credits(solo)).toBe(750);
    await handle.ctx.tournaments.tick();
    expect((await call(solo, 'GET', `/tournaments/${id}`)).json().status).toBe('CANCELLED');
    expect(await credits(solo)).toBe(1000);
  });
});
