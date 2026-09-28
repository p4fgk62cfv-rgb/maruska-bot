import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { buildApp, type AppHandle } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { createContext } from '../src/context.js';
import { createDb, type Db } from '../src/db.js';
import { redactUrl } from '../src/lib/security.js';
import { signInitData } from '../src/telegram/initData.js';
import { Bot } from './bots.js';

const url = process.env.TEST_DATABASE_URL;
const BOT_TOKEN = '123456:TEST-token-for-security';

describe('redaction', () => {
  it('removes tokens from URLs', () => {
    expect(redactUrl('/ws?token=abc.def')).toBe('/ws?token=[redacted]');
    expect(redactUrl('/x?a=1&token=abc&b=2')).toBe('/x?a=1&token=[redacted]&b=2');
  });
});

describe.skipIf(!url)('security', () => {
  let db: Db;
  let handle: AppHandle;
  let address: string;
  const logs: string[] = [];

  beforeAll(async () => {
    const config = loadConfig({ NODE_ENV: 'test', DATABASE_URL: url!, BOT_TOKEN, SESSION_SECRET: 's'.repeat(40), WEB_DIST: '/none', LOG_LEVEL: 'info' });
    db = createDb(url!);
    handle = await buildApp(createContext(config, db), { bot: null, logStream: { write: (line) => void logs.push(line) } });
    address = await handle.app.listen({ port: 0, host: '127.0.0.1' });
  });

  afterAll(async () => {
    await handle?.app.close();
    await db?.$disconnect();
  });

  it('never writes session tokens or initData to the logs', async () => {
    const initData = signInitData({ auth_date: String(Math.floor(Date.now() / 1000)), user: JSON.stringify({ id: 777_000_001, first_name: 'Лог' }) }, BOT_TOKEN);
    const { token, me } = (await handle.app.inject({ method: 'POST', url: '/api/auth/telegram', payload: { initData } })).json();
    const bot = new Bot('L', me.id, token, address);
    await bot.connect();
    await bot.send({ type: 'PING' });
    await handle.app.inject({ method: 'GET', url: '/api/me', headers: { authorization: `Bearer ${token}` } });
    bot.close();
    await new Promise((r) => setTimeout(r, 100));
    const all = logs.join('\n');
    expect(all).toContain('/ws?token=[redacted]');
    expect(all).not.toContain(token);
    expect(all).not.toContain(initData.slice(0, 40));
  });

  it('sends security headers and allows framing only by Telegram', async () => {
    const res = await handle.app.inject({ method: 'GET', url: '/health' });
    expect(res.headers['x-content-type-options']).toBe('nosniff');
    expect(String(res.headers['content-security-policy'])).toContain('frame-ancestors https://web.telegram.org');
  });
});
