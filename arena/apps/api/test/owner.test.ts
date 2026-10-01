import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { buildApp, type AppHandle } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { createContext } from '../src/context.js';
import { createDb, type Db } from '../src/db.js';
import { seedCatalog } from '../src/services/catalog.js';
import { signInitData } from '../src/telegram/initData.js';

const url = process.env.TEST_DATABASE_URL;
const BOT_TOKEN = '123456:TEST-token-for-owner';
const OWNER_TG = 970_000_000 + Math.floor(Math.random() * 1_000_000);
const RUN = Math.random().toString(36).slice(2, 10);

describe.skipIf(!url)('«Управление»: announcement and gifts, owner only', () => {
  let db: Db;
  let handle: AppHandle;
  let nextTg = OWNER_TG + 1;

  beforeAll(async () => {
    const config = loadConfig({
      NODE_ENV: 'test', DATABASE_URL: url!, BOT_TOKEN, SESSION_SECRET: 'o'.repeat(40), WEB_DIST: '/none', OWNER_IDS: `123, ${OWNER_TG}`,
    });
    db = createDb(url!);
    await seedCatalog(db);
    handle = await buildApp(createContext(config, db));
  });

  afterAll(async () => {
    await db.announcement.deleteMany({});
    await handle?.app.close();
    await db?.$disconnect();
  });

  async function login(name: string, tg = nextTg++): Promise<{ id: string; token: string; owner: boolean }> {
    const initData = signInitData({ auth_date: String(Math.floor(Date.now() / 1000)), user: JSON.stringify({ id: tg, first_name: name }) }, BOT_TOKEN);
    const res = await handle.app.inject({ method: 'POST', url: '/api/auth/telegram', payload: { initData }, remoteAddress: `10.3.${tg % 250}.${tg % 200}` });
    const { token, me } = res.json();
    return { id: me.id, token, owner: me.owner };
  }
  const call = (p: { token: string }, method: 'GET' | 'POST' | 'PUT' | 'DELETE', path: string, payload?: object) =>
    handle.app.inject({ method, url: `/api${path}`, payload, headers: { authorization: `Bearer ${p.token}` } });

  it('only the owner sees «Управление» and can use it', async () => {
    const owner = await login('Стас', OWNER_TG);
    const player = await login('Игрок');
    expect(owner.owner).toBe(true);
    expect(player.owner).toBe(false);
    for (const [method, path, body] of [
      ['PUT', '/owner/announcement', { text: 'взлом' }],
      ['DELETE', '/owner/announcement', undefined],
      ['GET', '/owner/players', undefined],
      ['POST', `/owner/players/${player.id}/wallet`, { currency: 'COINS', amount: 1000, requestId: 'hack-attempt-1' }],
      ['POST', `/owner/players/${player.id}/items`, { key: 'back_wolf' }],
    ] as const) {
      expect((await call(player, method, path, body)).statusCode, `${method} ${path}`).toBe(403);
    }
  });

  it('publishes an announcement everyone reads; a new one gets a new id', async () => {
    const owner = await login('Стас', OWNER_TG);
    const player = await login('Читатель');
    const first = (await call(owner, 'PUT', '/owner/announcement', { title: 'Турнир', text: 'В субботу в 20:00' })).json();
    expect((await call(player, 'GET', '/announcement')).json()).toMatchObject({ id: first.id, title: 'Турнир', text: 'В субботу в 20:00' });
    const second = (await call(owner, 'PUT', '/owner/announcement', { text: 'Перенесли на воскресенье' })).json();
    expect(second.id).not.toBe(first.id);
    expect((await call(player, 'GET', '/announcement')).json()).toMatchObject({ id: second.id, title: '', text: 'Перенесли на воскресенье' });
    await call(owner, 'DELETE', '/owner/announcement');
    expect((await call(player, 'GET', '/announcement')).json()).toBeNull();
  });

  it('gives and takes credits, coins and items', async () => {
    const owner = await login('Стас', OWNER_TG);
    const player = await login('Счастливчик');
    const found = (await call(owner, 'GET', '/owner/players?q=Счастливчик')).json() as { id: string; coins: number }[];
    expect(found.map((p) => p.id)).toContain(player.id);

    const coins = await call(owner, 'POST', `/owner/players/${player.id}/wallet`, { currency: 'COINS', amount: 500, requestId: `gift-coins-${RUN}` });
    expect(coins.json()).toEqual({ balance: 500 });
    // The same request repeated (double tap) does not pay twice.
    await call(owner, 'POST', `/owner/players/${player.id}/wallet`, { currency: 'COINS', amount: 500, requestId: `gift-coins-${RUN}` });
    const credits = await call(owner, 'POST', `/owner/players/${player.id}/wallet`, { currency: 'CREDITS', amount: -450, requestId: `take-credits-${RUN}` });
    expect(credits.json()).toEqual({ balance: 1_000 });
    const me = (await call(player, 'GET', '/me')).json();
    expect(me.wallet).toMatchObject({ coins: 500, credits: 1_000 });

    expect((await call(owner, 'POST', `/owner/players/${player.id}/items`, { key: 'back_wolf' })).json()).toEqual({ ok: true });
    const items = (await call(owner, 'GET', `/owner/players/${player.id}/items`)).json() as { key: string; owned: boolean }[];
    expect(items.find((i) => i.key === 'back_wolf')?.owned).toBe(true);
    expect((await call(player, 'POST', '/items/back_wolf/equip')).json()).toMatchObject({ cardBack: 'back_wolf' });
    await call(owner, 'POST', `/owner/players/${player.id}/items`, { key: 'back_wolf', take: true });
    const after = (await call(owner, 'GET', `/owner/players/${player.id}/items`)).json() as { key: string; owned: boolean }[];
    expect(after.find((i) => i.key === 'back_wolf')?.owned).toBe(false);
  });
});
