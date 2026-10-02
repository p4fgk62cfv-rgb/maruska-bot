import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import type { RoomSettings } from '@arena/shared';
import { buildApp, type AppHandle } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { createContext } from '../src/context.js';
import { createDb, type Db } from '../src/db.js';
import { seedCatalog } from '../src/services/catalog.js';
import { signInitData } from '../src/telegram/initData.js';

const url = process.env.TEST_DATABASE_URL;
const BOT_TOKEN = '123456:TEST-token-for-admin';
const SECRET = 'internal-secret-admin-123';
const ROOM: Omit<RoomSettings, 'password'> = {
  stake: 100, players: 3, deckSize: 36, speed: 'fast', variant: 'podkidnoy', throwIn: 'all', fairness: 'fair', ending: 'classic', server: 'almaz', isPrivate: false,
};

describe.skipIf(!url)('admin panel API («🃏 Арена» in the bot)', () => {
  let db: Db;
  let handle: AppHandle;
  let nextTg = 970_000_000 + Math.floor(Math.random() * 10_000_000);

  beforeAll(async () => {
    const config = loadConfig({
      NODE_ENV: 'test', DATABASE_URL: url!, BOT_TOKEN, SESSION_SECRET: 'a'.repeat(40), WEB_DIST: '/none', INTERNAL_API_SECRET: SECRET,
      BOT_USERNAME: 'maruska_bot', MINI_APP_SHORT_NAME: 'arena', TELEGRAM_API_URL: '',
    });
    db = createDb(url!);
    await seedCatalog(db);
    handle = await buildApp(createContext(config, db));
  });

  afterAll(async () => {
    await handle?.app.close();
    await db?.$disconnect();
  });

  async function player(name: string) {
    const tg = nextTg++;
    const initData = signInitData({ auth_date: String(Math.floor(Date.now() / 1000)), user: JSON.stringify({ id: tg, first_name: name, username: `u${tg}` }) }, BOT_TOKEN);
    const res = await handle.app.inject({ method: 'POST', url: '/api/auth/telegram', payload: { initData }, remoteAddress: `10.3.${tg % 250}.${tg % 200}` });
    const { token, me } = res.json();
    return { id: me.id as string, token: token as string, tg };
  }
  const admin = (method: 'GET' | 'POST', path: string, payload?: object, secret = SECRET) =>
    handle.app.inject({ method, url: `/api/internal/admin${path}`, payload, headers: { authorization: `Bearer ${secret}` } });
  const call = (p: { token: string }, method: 'GET' | 'POST', path: string, payload?: object) =>
    handle.app.inject({ method, url: `/api${path}`, payload, headers: { authorization: `Bearer ${p.token}` } });

  it('refuses without the shared secret', async () => {
    expect((await admin('GET', '/overview', undefined, 'wrong-secret-wrong-secret')).statusCode).toBe(401);
  });

  it('finds a player and changes money, premium, name and items', async () => {
    const p = await player('Проверка');
    await call(p, 'GET', '/me');
    expect((await admin('GET', '/overview')).json()).toMatchObject({ players: expect.any(Number), online: expect.any(Number) });

    const found = (await admin('GET', `/players?q=${p.tg}`)).json();
    expect(found).toHaveLength(1);
    expect(found[0]).toMatchObject({ telegramId: String(p.tg), name: 'Проверка', credits: 1450 });
    expect((await admin('GET', `/players?q=@u${p.tg}`)).json()[0].telegramId).toBe(String(p.tg));

    const credit = await admin('POST', `/players/${p.tg}/wallet`, { currency: 'CREDITS', amount: 5000, reason: 'компенсация', requestId: `req-${p.tg}-1`, admin: 'Owner' });
    expect(credit.json()).toEqual({ balance: 6450 });
    // Same request id again: applied once.
    await admin('POST', `/players/${p.tg}/wallet`, { currency: 'CREDITS', amount: 5000, reason: 'компенсация', requestId: `req-${p.tg}-1` });
    expect((await admin('POST', `/players/${p.tg}/wallet`, { currency: 'CREDITS', amount: -999_999, reason: 'списание', requestId: `req-${p.tg}-2` })).json()).toMatchObject({ error: 'INSUFFICIENT_FUNDS' });
    expect((await admin('POST', `/players/${p.tg}/wallet`, { currency: 'CREDITS', amount: -450, reason: 'списание', requestId: `req-${p.tg}-3` })).json()).toEqual({ balance: 6000 });

    expect((await admin('POST', `/players/${p.tg}/premium`, { days: 30 })).json().premiumUntil).toBeTruthy();
    await call(p, 'POST', '/me/avatar'); // no body: rejected, nothing changes
    await db.profile.update({ where: { userId: p.id }, data: { nickname: 'Плохое имя' } });
    await admin('POST', `/players/${p.tg}/reset`, { what: 'nickname' });
    await admin('POST', `/players/${p.tg}/items`, { key: 'back_wolf' });

    const card = (await admin('GET', `/players/${p.tg}`)).json();
    expect(card).toMatchObject({ name: 'Проверка', nickname: null, wallet: { CREDITS: 6000 }, stats: { games: 0 } });
    expect(card.items.map((i: { key: string }) => i.key)).toContain('back_wolf');
    expect(card.transactions[0]).toMatchObject({ type: 'ADMIN', amount: -450 });
    expect(card.premiumUntil).toBeTruthy();
    expect((await call(p, 'POST', '/items/back_wolf/equip')).json()).toMatchObject({ cardBack: 'back_wolf' });
  });

  it('shows live tables and closes a waiting one', async () => {
    const host = await player('Хозяин');
    const room = (await call(host, 'POST', '/rooms', ROOM)).json().room;
    const live = (await admin('GET', '/live')).json();
    expect(live.rooms.some((r: { id: string }) => r.id === room.id)).toBe(true);
    expect((await admin('POST', `/rooms/${room.id}/close`)).json()).toEqual({ ok: true });
    expect((await admin('GET', '/live')).json().rooms.some((r: { id: string }) => r.id === room.id)).toBe(false);
    expect((await admin('POST', `/rooms/${room.id}/close`)).statusCode).toBe(404);
  });

  it('runs tournaments, seasons and shop prices', async () => {
    const created = await handle.app.inject({
      method: 'POST', url: '/api/internal/tournaments', headers: { authorization: `Bearer ${SECRET}` },
      payload: { title: `Проверка ${nextTg}`, entryFee: 0, maxPlayers: 8, startsAt: new Date(Date.now() + 3600_000).toISOString() },
    });
    const tid = created.json().id as string;
    expect((await admin('GET', '/tournaments')).json().some((t: { id: string }) => t.id === tid)).toBe(true);
    expect((await admin('POST', `/tournaments/${tid}/cancel`)).json()).toEqual({ ok: true });
    expect((await admin('POST', `/tournaments/${tid}/cancel`)).statusCode).toBe(404);

    const year = 2100 + (nextTg % 500);
    // Earlier runs against the same database may have left a season in that year.
    await db.season.deleteMany({ where: { startsAt: { gte: new Date(`${year}-01-01T00:00:00Z`), lt: new Date(`${year + 1}-01-01T00:00:00Z`) } } });
    const season = await admin('POST', '/seasons', { title: `Сезон ${year}`, startsAt: `${year}-01-01T00:00:00Z`, endsAt: `${year}-03-01T00:00:00Z` });
    expect(season.json().id).toBeTruthy();
    expect((await admin('POST', '/seasons', { title: 'Наложение', startsAt: `${year}-02-01T00:00:00Z`, endsAt: `${year}-04-01T00:00:00Z` })).statusCode).toBe(400);

    expect((await admin('POST', '/items/back_tartan', { price: 3000, name: 'Шотландка+' })).json()).toEqual({ ok: true });
    await seedCatalog(db);
    const item = (await admin('GET', '/items')).json().find((i: { key: string }) => i.key === 'back_tartan');
    expect(item).toMatchObject({ price: 3000, name: 'Шотландка+', overridden: true });
    await db.item.update({ where: { key: 'back_tartan' }, data: { adminOverride: false } });
    await seedCatalog(db);
  });

  it('broadcasts to players through the bot outbox', async () => {
    const dry = (await admin('POST', '/broadcast', { text: 'Турнир в 20:00!', audience: 'active7', dryRun: true })).json();
    expect(dry.recipients).toBeGreaterThan(0);
    const before = await db.notification.count({ where: { kind: 'broadcast' } });
    const sent = (await admin('POST', '/broadcast', { text: 'Турнир в 20:00!', audience: 'active7' })).json();
    expect(await db.notification.count({ where: { kind: 'broadcast' } })).toBe(before + sent.recipients);
    expect((await admin('GET', '/settings')).json()).toMatchObject({ rakePercent: 5, signupBonus: 1450 });
  });
});
