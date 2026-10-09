import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { STAR_PACKS } from '@arena/shared';
import { buildApp, type AppHandle } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { createContext } from '../src/context.js';
import { createDb, type Db } from '../src/db.js';
import { seedCatalog } from '../src/services/catalog.js';
import { TelegramBot, type StarTransaction } from '../src/services/notifier.js';
import { signInitData } from '../src/telegram/initData.js';

const url = process.env.TEST_DATABASE_URL;
const BOT_TOKEN = '123456:TEST-token-for-stars';
const SECRET = 'internal-secret-stars';
const OWNER_TG = 880_100_001;

describe('star packs', () => {
  it('sell coins only, more per star in bigger packs', () => {
    const keys = new Set(STAR_PACKS.map((p) => p.key));
    expect(keys.size).toBe(STAR_PACKS.length);
    for (let i = 1; i < STAR_PACKS.length; i++) {
      expect(STAR_PACKS[i]!.coins / STAR_PACKS[i]!.stars).toBeGreaterThanOrEqual(STAR_PACKS[i - 1]!.coins / STAR_PACKS[i - 1]!.stars);
    }
  });
});

describe.skipIf(!url)('Telegram Stars', () => {
  let db: Db;
  let handle: AppHandle;
  const calls: { method: string; body: Record<string, unknown> }[] = [];
  let transactions: StarTransaction[] = [];
  let telegramUp = true;
  let nextTg = 720_000_000 + Math.floor(Math.random() * 10_000_000);

  beforeAll(async () => {
    const config = loadConfig({
      NODE_ENV: 'test', DATABASE_URL: url!, BOT_TOKEN, SESSION_SECRET: 's'.repeat(40), WEB_DIST: '/none',
      INTERNAL_API_SECRET: SECRET, OWNER_IDS: String(OWNER_TG), AUTH_RATE_LIMIT: '100',
    });
    db = createDb(url!);
    await seedCatalog(db);
    await db.setting.deleteMany({ where: { key: 'stars_sweep_offset' } });
    const fakeFetch = (async (address: string, init?: RequestInit) => {
      const method = address.split('/').at(-1)!;
      const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
      calls.push({ method, body });
      if (!telegramUp && method !== 'sendMessage') return new Response('{"ok":false}', { status: 502 });
      const result =
        method === 'createInvoiceLink' ? `https://t.me/$invoice-${calls.length}`
        : method === 'refundStarPayment' ? true
        : method === 'getStarTransactions' ? { transactions: transactions.slice(Number(body.offset), Number(body.offset) + Number(body.limit)) }
        : {};
      return new Response(JSON.stringify({ ok: true, result }), { status: 200 });
    }) as typeof fetch;
    handle = await buildApp(createContext(config, db), { bot: new TelegramBot(BOT_TOKEN, 'http://fake', fakeFetch) });
  });

  afterAll(async () => {
    await db?.setting.deleteMany({ where: { key: 'stars_sweep_offset' } });
    await handle?.app.close();
    await db?.$disconnect();
  });

  async function login(tg = nextTg++) {
    const initData = signInitData({ auth_date: String(Math.floor(Date.now() / 1000)), user: JSON.stringify({ id: tg, first_name: `Buyer${tg}` }) }, BOT_TOKEN);
    const res = await handle.app.inject({ method: 'POST', url: '/api/auth/telegram', payload: { initData } });
    expect(res.statusCode).toBe(200);
    const { token, me } = res.json() as { token: string; me: { id: string } };
    return { token, id: me.id, tg };
  }

  const coins = async (userId: string) =>
    Number((await db.wallet.findUniqueOrThrow({ where: { userId_currency: { userId, currency: 'COINS' } } })).balance);

  const order = async (token: string, pack = 'coins_160') => {
    const res = await handle.app.inject({ method: 'POST', url: '/api/stars/orders', headers: { authorization: `Bearer ${token}` }, payload: { pack } });
    expect(res.statusCode).toBe(200);
    return res.json() as { order: { id: string; stars: number; coins: number }; link: string };
  };

  const internal = (path: string, payload: Record<string, unknown>) =>
    handle.app.inject({ method: 'POST', url: `/api/internal/stars/${path}`, headers: { authorization: `Bearer ${SECRET}` }, payload });

  it('makes an XTR invoice for a pack, priced by the server', async () => {
    const p = await login();
    const { order: o, link } = await order(p.token);
    expect(link).toMatch(/^https:\/\/t\.me\/\$invoice/);
    expect(o).toMatchObject({ stars: 75, coins: 160 });
    const invoice = calls.findLast((c) => c.method === 'createInvoiceLink')!.body;
    expect(invoice).toMatchObject({ currency: 'XTR', payload: `arena:${o.id}`, prices: [{ label: '160 монет', amount: 75 }] });
    expect((await handle.app.inject({ method: 'POST', url: '/api/stars/orders', headers: { authorization: `Bearer ${p.token}` }, payload: { pack: 'credits_1m' } })).statusCode).toBe(404);
  });

  it('checks the payment, credits it once, and shows the order as paid', async () => {
    const p = await login();
    const before = await coins(p.id);
    const { order: o } = await order(p.token);
    const payload = `arena:${o.id}`;

    expect((await internal('precheckout', { payload, telegramId: p.tg, stars: 75, currency: 'XTR' })).json()).toEqual({ ok: true });
    expect((await internal('precheckout', { payload, telegramId: p.tg + 1, stars: 75, currency: 'XTR' })).json()).toMatchObject({ ok: false });
    expect((await internal('precheckout', { payload, telegramId: p.tg, stars: 1, currency: 'XTR' })).json()).toMatchObject({ ok: false });
    expect((await internal('precheckout', { payload: 'arena:nope', telegramId: p.tg, stars: 75, currency: 'XTR' })).json()).toMatchObject({ ok: false });

    // The same notice twice at once: one credit.
    const notice = { payload, telegramId: p.tg, stars: 75, chargeId: `charge-${o.id}` };
    const [a, b] = await Promise.all([internal('paid', notice), internal('paid', notice)]);
    expect([a.statusCode, b.statusCode]).toEqual([200, 200]);
    expect([a.json().credited, b.json().credited].sort()).toEqual([false, true]);
    expect(await coins(p.id)).toBe(before + 160);

    const status = await handle.app.inject({ method: 'GET', url: `/api/stars/orders/${o.id}`, headers: { authorization: `Bearer ${p.token}` } });
    expect(status.json()).toMatchObject({ status: 'PAID', coins: 160 });
    // Paid already: a second payment of the same invoice is refused.
    expect((await internal('precheckout', { payload, telegramId: p.tg, stars: 75, currency: 'XTR' })).json()).toMatchObject({ ok: false });

    // Someone else cannot look at it.
    const other = await login();
    expect((await handle.app.inject({ method: 'GET', url: `/api/stars/orders/${o.id}`, headers: { authorization: `Bearer ${other.token}` } })).statusCode).toBe(404);
  });

  it('the sweep credits a payment whose notice was lost, and only once', async () => {
    const p = await login();
    const before = await coins(p.id);
    const { order: o } = await order(p.token, 'coins_50');
    transactions.push({ id: `charge-sweep-${o.id}`, amount: 25, date: 0, source: { type: 'user', user: { id: p.tg }, invoice_payload: `arena:${o.id}` } });
    transactions.push({ id: 'other-bot-sale', amount: 10, date: 0, source: { type: 'user', user: { id: p.tg }, invoice_payload: 'bot:something' } });
    expect(await handle.ctx.stars.sweep()).toBe(1);
    expect(await coins(p.id)).toBe(before + 50);
    expect(await handle.ctx.stars.sweep()).toBe(0);
    expect(await coins(p.id)).toBe(before + 50);
    const offset = await db.setting.findUnique({ where: { key: 'stars_sweep_offset' } });
    expect(offset?.value).toBe(transactions.length);
  });

  it('owner sees the purchases and refunds one: stars back, coins taken back', async () => {
    const buyer = await login();
    const before = await coins(buyer.id);
    const { order: o } = await order(buyer.token, 'coins_350');
    await internal('paid', { payload: `arena:${o.id}`, telegramId: buyer.tg, stars: 150, chargeId: `charge-refund-${o.id}` });
    expect(await coins(buyer.id)).toBe(before + 350);

    const owner = await login(OWNER_TG);
    const list = await handle.app.inject({ method: 'GET', url: '/api/owner/stars', headers: { authorization: `Bearer ${owner.token}` } });
    expect(list.statusCode).toBe(200);
    expect(list.json().orders.some((x: { id: string }) => x.id === o.id)).toBe(true);
    expect(list.json().totals.all).toBeGreaterThanOrEqual(150);
    expect((await handle.app.inject({ method: 'GET', url: '/api/owner/stars', headers: { authorization: `Bearer ${buyer.token}` } })).statusCode).toBe(403);

    const refund = await handle.app.inject({ method: 'POST', url: `/api/owner/stars/${o.id}/refund`, headers: { authorization: `Bearer ${owner.token}` } });
    expect(refund.json()).toMatchObject({ status: 'REFUNDED' });
    expect(calls.findLast((c) => c.method === 'refundStarPayment')!.body).toEqual({ user_id: buyer.tg, telegram_payment_charge_id: `charge-refund-${o.id}` });
    expect(await coins(buyer.id)).toBe(before);
    expect((await handle.app.inject({ method: 'POST', url: `/api/owner/stars/${o.id}/refund`, headers: { authorization: `Bearer ${owner.token}` } })).statusCode).toBe(409);
  });

  it('no invoice when Telegram does not answer, and nothing left behind', async () => {
    const p = await login();
    telegramUp = false;
    try {
      const res = await handle.app.inject({ method: 'POST', url: '/api/stars/orders', headers: { authorization: `Bearer ${p.token}` }, payload: { pack: 'coins_50' } });
      expect(res.statusCode).toBe(503);
      expect(await db.starOrder.count({ where: { userId: p.id } })).toBe(0);
    } finally {
      telegramUp = true;
    }
  });

  it('the bot endpoints need the internal secret', async () => {
    const res = await handle.app.inject({ method: 'POST', url: '/api/internal/stars/paid', payload: { payload: 'arena:x', telegramId: 1, stars: 1, chargeId: 'x' } });
    expect(res.statusCode).toBe(401);
  });
});
