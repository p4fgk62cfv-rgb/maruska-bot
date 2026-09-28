import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { buildApp, type AppHandle } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { createContext } from '../src/context.js';
import { createDb, type Db } from '../src/db.js';
import { seedCatalog } from '../src/services/catalog.js';
import { signInitData } from '../src/telegram/initData.js';

const url = process.env.TEST_DATABASE_URL;
const BOT_TOKEN = '123456:TEST-token-for-players';

describe.skipIf(!url)('opponent cards: stats, private labels, reports', () => {
  let db: Db;
  let handle: AppHandle;
  let nextTg = 950_000_000 + Math.floor(Math.random() * 10_000_000);

  beforeAll(async () => {
    const config = loadConfig({
      NODE_ENV: 'test', DATABASE_URL: url!, BOT_TOKEN, SESSION_SECRET: 'p'.repeat(40), WEB_DIST: '/none', INTERNAL_API_SECRET: 'internal-secret-123',
    });
    db = createDb(url!);
    await seedCatalog(db);
    handle = await buildApp(createContext(config, db));
  });

  afterAll(async () => {
    await handle?.app.close();
    await db?.$disconnect();
  });

  async function player(name: string): Promise<{ id: string; token: string; tg: number }> {
    const tg = nextTg++;
    const initData = signInitData({ auth_date: String(Math.floor(Date.now() / 1000)), user: JSON.stringify({ id: tg, first_name: name }) }, BOT_TOKEN);
    const res = await handle.app.inject({ method: 'POST', url: '/api/auth/telegram', payload: { initData }, remoteAddress: `10.2.${tg % 250}.${tg % 200}` });
    const { token, me } = res.json();
    return { id: me.id, token, tg };
  }
  const call = (p: { token: string }, method: 'GET' | 'POST' | 'PUT' | 'DELETE', path: string, payload?: object) =>
    handle.app.inject({ method, url: `/api${path}`, payload, headers: { authorization: `Bearer ${p.token}` } });

  it('shows season and total stats, and a label only its author sees', async () => {
    const [me, rival, other] = [await player('Я'), await player('Соперник'), await player('Третий')];
    await db.profile.update({ where: { userId: rival.id }, data: { gamesPlayed: 10, gamesWon: 7, gamesLost: 3, totalWinnings: 17_500n, rating: 321 } });

    const card = (await call(me, 'GET', `/players/${rival.id}/card`)).json();
    expect(card).toMatchObject({ id: rival.id, name: 'Соперник', relation: 'none', note: null, total: { wins: 7, games: 10, winnings: 17_500, winRate: 70, rating: 321 } });
    expect(Array.isArray(card.achievements)).toBe(true);

    expect((await call(me, 'PUT', `/players/${rival.id}/note`, { text: '  тянет  время ' })).json()).toEqual({ note: 'тянет время' });
    expect((await call(me, 'GET', `/players/${rival.id}/card`)).json().note).toBe('тянет время');
    expect((await call(other, 'GET', `/players/${rival.id}/card`)).json().note).toBeNull();
    expect((await call(me, 'GET', `/players/notes?ids=${rival.id},${other.id}`)).json()).toEqual({ [rival.id]: 'тянет время' });
    expect((await call(other, 'GET', `/players/notes?ids=${rival.id}`)).json()).toEqual({});
    expect((await call(me, 'PUT', `/players/${rival.id}/note`, { text: 'x'.repeat(41) })).statusCode).toBe(400);
    expect((await call(me, 'PUT', `/players/${rival.id}/note`, { text: '' })).json()).toEqual({ note: null });
    expect((await call(me, 'GET', `/players/${rival.id}/card`)).json().note).toBeNull();
  });

  it('stores one report a day per reporter and lists them for moderators', async () => {
    const [a, b, target] = [await player('A'), await player('B'), await player('Нарушитель')];
    expect((await call(a, 'POST', `/players/${target.id}/report`, { reason: 'cheating' })).json()).toEqual({ ok: true });
    expect((await call(a, 'POST', `/players/${target.id}/report`, { reason: 'insult' })).statusCode).toBe(200);
    expect((await call(b, 'POST', `/players/${target.id}/report`, { reason: 'collusion' })).statusCode).toBe(200);
    expect((await call(a, 'POST', `/players/${a.id}/report`, { reason: 'other' })).statusCode).toBe(400);
    expect(await db.playerReport.count({ where: { targetId: target.id } })).toBe(2);

    const list = (
      await handle.app.inject({ method: 'GET', url: '/api/internal/moderation/reports', headers: { authorization: 'Bearer internal-secret-123' } })
    ).json() as { telegramId: string; reporters: number; reasons: Record<string, number> }[];
    const row = list.find((r) => r.telegramId === String(target.tg));
    expect(row).toMatchObject({ reporters: 2, reasons: { CHEATING: 1, COLLUSION: 1 } });
  });

  it('lets a player pick an in-game name and upload an avatar that everyone sees', async () => {
    const [me, rival] = [await player('Станислав'), await player('Соперник')];
    expect((await call(me, 'PUT', '/me/nickname', { nickname: '  Стас 🃏 ' })).json()).toMatchObject({ name: 'Стас 🃏', nickname: 'Стас 🃏', telegramName: 'Станислав' });
    expect((await call(rival, 'GET', `/players/${me.id}/card`)).json().name).toBe('Стас 🃏');
    for (const bad of ['x', 'Админ Маруськи', '<b>hi</b>', 'a'.repeat(21)]) {
      expect((await call(me, 'PUT', '/me/nickname', { nickname: bad })).statusCode).toBe(400);
    }
    expect((await call(me, 'PUT', '/me/nickname', { nickname: '' })).json()).toMatchObject({ name: 'Станислав', nickname: null });

    // 1×1 PNG
    const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=', 'base64');
    const up = (await call(me, 'POST', '/me/avatar', { image: `data:image/png;base64,${png.toString('base64')}` })).json();
    expect(up.customAvatar).toBe(true);
    expect(up.photoUrl).toBe(`/api/avatars/${me.id}?v=1`);
    const img = await handle.app.inject({ method: 'GET', url: `/api/avatars/${me.id}` });
    expect(img.statusCode).toBe(200);
    expect(img.headers['content-type']).toBe('image/png');
    expect(img.rawPayload.equals(png)).toBe(true);
    expect((await call(rival, 'GET', `/players/${me.id}/card`)).json().photoUrl).toBe(`/api/avatars/${me.id}?v=1`);
    expect((await call(me, 'POST', '/me/avatar', { image: `data:image/png;base64,${png.toString('base64')}` })).json().photoUrl).toBe(`/api/avatars/${me.id}?v=2`);

    // Not a picture, whatever the declared type says.
    const fake = Buffer.from('<svg onload=alert(1)>').toString('base64');
    expect((await call(me, 'POST', '/me/avatar', { image: `data:image/png;base64,${fake}` })).statusCode).toBe(400);

    const back = (await call(me, 'DELETE', '/me/avatar')).json();
    expect(back).toMatchObject({ customAvatar: false, photoUrl: null });
    expect((await handle.app.inject({ method: 'GET', url: `/api/avatars/${me.id}` })).statusCode).toBe(404);
  });
});
