import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { buildApp, type AppHandle } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { createContext } from '../src/context.js';
import { createDb, type Db } from '../src/db.js';
import { seedCatalog } from '../src/services/catalog.js';

const url = process.env.TEST_DATABASE_URL;
const SECRET = 'internal-secret-applogin-1';

describe.skipIf(!url)('sign-in for the installed app (confirmed in the bot)', () => {
  let db: Db;
  let handle: AppHandle;
  let nextTg = 600_000_000 + Math.floor(Math.random() * 10_000_000);

  beforeAll(async () => {
    const config = loadConfig({
      NODE_ENV: 'test', DATABASE_URL: url!, BOT_TOKEN: '123456:TEST-token-applogin', SESSION_SECRET: 'a'.repeat(40), WEB_DIST: '/none',
      BOT_USERNAME: 'maruska_bot', INTERNAL_API_SECRET: SECRET,
    });
    db = createDb(url!);
    await seedCatalog(db);
    handle = await buildApp(createContext(config, db), { bot: null });
  });

  afterAll(async () => {
    await handle?.app.close();
    await db?.$disconnect();
  });

  const post = (path: string, payload: object, headers: Record<string, string> = {}) => handle.app.inject({ method: 'POST', url: `/api${path}`, payload, headers });
  const bot = { authorization: `Bearer ${SECRET}` };
  const tgUser = (name: string) => ({ id: nextTg++, first_name: name, username: `u${nextTg}` });

  it('start → confirm in the bot → the app gets a session, once', async () => {
    const start = (await post('/auth/app/start', { device: 'Android · Chrome' })).json();
    expect(start.link).toBe(`https://t.me/maruska_bot?start=alogin_${start.id}`);
    expect((await post('/auth/app/poll', { id: start.id, secret: start.secret })).json()).toEqual({ status: 'pending' });

    // The bot shows the device, then the person confirms.
    const info = await handle.app.inject({ method: 'GET', url: `/api/internal/app-login/${start.id}`, headers: bot });
    expect(info.json()).toMatchObject({ device: 'Android · Chrome', confirmed: false });
    const user = tgUser('Вася');
    expect((await post(`/internal/app-login/${start.id}/confirm`, { user }, bot)).json()).toEqual({ name: 'Вася' });

    const done = (await post('/auth/app/poll', { id: start.id, secret: start.secret })).json();
    expect(done.status).toBe('done');
    expect(done.me.firstName).toBe('Вася');
    const me = await handle.app.inject({ method: 'GET', url: '/api/me', headers: { authorization: `Bearer ${done.token}` } });
    expect(me.json().id).toBe(done.me.id);

    // Only once.
    expect((await post('/auth/app/poll', { id: start.id, secret: start.secret })).statusCode).toBe(404);
  });

  it('the link alone is not enough, a confirmed request cannot be taken over, the bot needs the secret', async () => {
    const start = (await post('/auth/app/start', {})).json();
    const owner = tgUser('Петя');
    await post(`/internal/app-login/${start.id}/confirm`, { user: owner }, bot);
    // Someone who saw the link but not the secret.
    expect((await post('/auth/app/poll', { id: start.id, secret: 'x'.repeat(32) })).statusCode).toBe(404);
    // Another Telegram account cannot re-confirm it for themselves.
    expect((await post(`/internal/app-login/${start.id}/confirm`, { user: tgUser('Чужой') }, bot)).statusCode).toBe(403);
    // Without the bot's key: refused.
    expect((await post(`/internal/app-login/${start.id}/confirm`, { user: owner })).statusCode).toBe(401);
    // The rightful device still signs in as the first confirmer.
    expect((await post('/auth/app/poll', { id: start.id, secret: start.secret })).json().me.firstName).toBe('Петя');
  });

  it('an existing player keeps their account; expired requests and banned players are refused', async () => {
    const user = tgUser('Старый');
    const first = (await post('/auth/app/start', {})).json();
    await post(`/internal/app-login/${first.id}/confirm`, { user }, bot);
    const a = (await post('/auth/app/poll', { id: first.id, secret: first.secret })).json();
    const second = (await post('/auth/app/start', {})).json();
    await post(`/internal/app-login/${second.id}/confirm`, { user }, bot);
    const b = (await post('/auth/app/poll', { id: second.id, secret: second.secret })).json();
    expect(b.me.id).toBe(a.me.id);

    const old = (await post('/auth/app/start', {})).json();
    await db.loginRequest.update({ where: { id: old.id }, data: { expiresAt: new Date(Date.now() - 1000) } });
    expect((await post(`/internal/app-login/${old.id}/confirm`, { user }, bot)).statusCode).toBe(404);
    expect((await post('/auth/app/poll', { id: old.id, secret: old.secret })).statusCode).toBe(404);

    await db.user.update({ where: { id: a.me.id }, data: { bannedAt: new Date() } });
    const banned = (await post('/auth/app/start', {})).json();
    expect((await post(`/internal/app-login/${banned.id}/confirm`, { user }, bot)).json().error).toBe('BANNED');
    await db.user.update({ where: { id: a.me.id }, data: { bannedAt: null } });
  });
});
