import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import type { RoomSettings } from '@arena/shared';
import { buildApp, type AppHandle } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { createContext } from '../src/context.js';
import { createDb, type Db } from '../src/db.js';
import { journal } from '../src/lib/journal.js';
import { seedCatalog } from '../src/services/catalog.js';
import { signInitData } from '../src/telegram/initData.js';
import { Bot } from './bots.js';

const url = process.env.TEST_DATABASE_URL;
const BOT_TOKEN = '123456:TEST-token-for-journal';
const OWNER_TG = 960_000_000 + Math.floor(Math.random() * 1_000_000);

const SETTINGS: Omit<RoomSettings, 'password'> = {
  stake: 100, players: 2, deckSize: 36, speed: 'fast', variant: 'podkidnoy', throwIn: 'all',
  fairness: 'fair', ending: 'classic', server: 'almaz', isPrivate: false,
};

describe.skipIf(!url)('«Журнал» for the owner: games, problems and their causes', () => {
  let db: Db;
  let handle: AppHandle;
  let address: string;
  let nextTg = OWNER_TG + 1;
  const sockets: Bot[] = [];

  beforeAll(async () => {
    const config = loadConfig({ NODE_ENV: 'test', DATABASE_URL: url!, BOT_TOKEN, SESSION_SECRET: 'j'.repeat(40), WEB_DIST: '/none', OWNER_IDS: String(OWNER_TG) });
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

  async function login(name: string, tg = nextTg++): Promise<{ id: string; token: string }> {
    const initData = signInitData({ auth_date: String(Math.floor(Date.now() / 1000)), user: JSON.stringify({ id: tg, first_name: name }) }, BOT_TOKEN);
    const res = await handle.app.inject({ method: 'POST', url: '/api/auth/telegram', payload: { initData }, remoteAddress: `10.9.${tg % 250}.${tg % 200}` });
    const { token, me } = res.json();
    return { id: me.id, token };
  }
  const get = (token: string, path: string) => handle.app.inject({ method: 'GET', url: `/api${path}`, headers: { authorization: `Bearer ${token}` } });

  it('a game with a dropped connection and a refused move is in the journal, with its cause', async () => {
    const owner = await login('Владелец', OWNER_TG);
    const anna = await login('Анна');
    const boris = await login('Борис');
    const a = new Bot('Анна', anna.id, anna.token, address);
    const b = new Bot('Борис', boris.id, boris.token, address);
    sockets.push(a, b);
    await a.connect();
    await b.connect();

    const created = await handle.app.inject({ method: 'POST', url: '/api/rooms', payload: { ...SETTINGS }, headers: { authorization: `Bearer ${anna.token}` } });
    const roomId: string = created.json().room.id;
    expect((await handle.app.inject({ method: 'POST', url: `/api/rooms/${roomId}/join`, payload: {}, headers: { authorization: `Bearer ${boris.token}` } })).statusCode).toBe(200);
    for (const p of [a, b]) expect((await p.send({ type: 'READY', roomId, ready: true })).type).toBe('ACK');
    const started = (await a.waitFor((m) => m.type === 'GAME_STARTED')) as { gameId: string };
    const gameId = started.gameId;

    // Борис plays a card from Анна's hand: the server refuses the move
    await a.waitFor((m) => m.type === 'GAME_STATE');
    const annaCard = a.view!.you!.hand[0]!;
    expect((await b.send({ type: 'PLAY_CARD', gameId, card: annaCard })).type).toBe('ERROR');
    // Борис loses the connection and comes back
    b.close();
    await new Promise((r) => setTimeout(r, 200));
    await b.connect();
    await new Promise((r) => setTimeout(r, 300));
    // Анна gives up
    expect((await a.send({ type: 'LEAVE_GAME', gameId })).type).toBe('ACK');
    await a.waitFor((m) => m.type === 'GAME_FINISHED');
    await journal.flush();

    // Only the owner can read the journal
    expect((await get(anna.token, '/owner/journal/summary')).statusCode).toBe(403);
    expect((await get(anna.token, `/owner/journal/games/${gameId}`)).statusCode).toBe(403);

    const list = (await get(owner.token, '/owner/journal/games?filter=problems')).json() as { id: string; reasonText: string; loser: string; flags: { offline: number } }[];
    const row = list.find((g) => g.id === gameId)!;
    expect(row).toBeDefined();
    expect(row.loser).toBe('Анна');
    expect(row.reasonText).toBe('сдался');
    expect(row.flags.offline).toBe(1);

    const game = (await get(owner.token, `/owner/journal/games/${gameId}`)).json() as { timeline: { who: string; text: string }[] };
    const lines = game.timeline.map((t) => `${t.who}: ${t.text}`);
    expect(lines.some((l) => l.startsWith('Борис: 🚫 ход отклонён'))).toBe(true);
    expect(lines).toContain('Борис: 📵 пропала связь');
    expect(lines).toContain('Борис: 📶 связь вернулась');
    expect(lines).toContain('Анна: сдался');

    const summary = (await get(owner.token, '/owner/journal/summary?hours=1')).json() as { games: number; problems: { refused: number; offline: number }; endings: { reason: string }[] };
    expect(summary.games).toBeGreaterThanOrEqual(1);
    expect(summary.problems.refused).toBeGreaterThanOrEqual(1);
    expect(summary.problems.offline).toBeGreaterThanOrEqual(1);
    expect(summary.endings.some((e) => e.reason === 'surrender')).toBe(true);

    expect((await get(owner.token, '/owner/journal/tournaments')).statusCode).toBe(200);
  }, 30_000);

  it('an error in a player\'s app reaches the journal (and a flood of them does not)', async () => {
    const owner = await login('Владелец', OWNER_TG);
    const vera = await login('Вера');
    const post = (payload: object) => handle.app.inject({ method: 'POST', url: '/api/client-error', payload, headers: { authorization: `Bearer ${vera.token}` } });
    expect((await handle.app.inject({ method: 'POST', url: '/api/client-error', payload: { kind: 'error', message: 'x' } })).statusCode).toBe(401);
    const report = { kind: 'render', message: 'Cannot read properties of undefined (reading \'hand\')', stack: 'at GameScreen', where: '#/game', version: 'test', agent: 'vitest' };
    expect((await post(report)).statusCode).toBe(200);
    for (let i = 0; i < 25; i++) await post({ ...report, message: `шум ${i}` });
    await journal.flush();

    const summary = (await get(owner.token, '/owner/journal/summary?hours=1')).json() as { problems: { clientErrors: number }; recent: { text: string }[] };
    expect(summary.recent.some((r) => r.text.startsWith('Вера: 🐞 ошибка в приложении: Cannot read properties'))).toBe(true);
    const mine = summary.recent.filter((r) => r.text.startsWith('Вера: 🐞'));
    expect(mine.length).toBeLessThanOrEqual(20);
    expect(summary.problems.clientErrors).toBeGreaterThanOrEqual(1);
  }, 30_000);
});
