import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import type { FastifyInstance } from 'fastify';
import { buildApp } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { createContext, type Context } from '../src/context.js';
import { createDb, type Db } from '../src/db.js';
import { seedCatalog } from '../src/services/catalog.js';
import { signInitData } from '../src/telegram/initData.js';

/** Runs against a real Postgres (migrated `arena` schema). Skipped when TEST_DATABASE_URL is not set. */
const url = process.env.TEST_DATABASE_URL;
const BOT_TOKEN = '123456:TEST-token-for-integration';

describe.skipIf(!url)('API + ledger on Postgres', () => {
  let db: Db;
  let ctx: Context;
  let app: FastifyInstance;
  const tgId = 700_000_000 + Math.floor(Math.random() * 1_000_000);

  beforeAll(async () => {
    const config = loadConfig({
      NODE_ENV: 'test',
      DATABASE_URL: url!,
      BOT_TOKEN,
      SESSION_SECRET: 's'.repeat(40),
      SIGNUP_BONUS_CHIPS: '10000',
      WEB_DIST: '/nonexistent',
    });
    db = createDb(url!);
    await seedCatalog(db);
    ctx = createContext(config, db);
    app = await buildApp(ctx);
  });

  afterAll(async () => {
    await app?.close();
    await db?.$disconnect();
  });

  async function login(id = tgId) {
    const initData = signInitData(
      {
        auth_date: String(Math.floor(Date.now() / 1000)),
        user: JSON.stringify({ id, first_name: 'Тест', last_name: 'Игрок', username: `t${id}` }),
        start_param: 'game_ROOM1234',
      },
      BOT_TOKEN,
    );
    return app.inject({ method: 'POST', url: '/api/auth/telegram', payload: { initData } });
  }

  it('logs in through Telegram, creates the account once and grants the signup bonus once', async () => {
    const first = await login();
    expect(first.statusCode).toBe(200);
    const body = first.json();
    expect(body.me.name).toBe('Тест Игрок');
    expect(body.me.wallet.chips).toBe(10_000);
    expect(body.startParam).toBe('game_ROOM1234');

    const second = (await login()).json();
    expect(second.me.id).toBe(body.me.id);
    expect(second.me.wallet.chips).toBe(10_000);

    const me = await app.inject({ method: 'GET', url: '/api/me', headers: { authorization: `Bearer ${body.token}` } });
    expect(me.json().stats.achievementsTotal).toBeGreaterThan(0);
  });

  it('refuses requests without a valid session or with forged initData', async () => {
    expect((await app.inject({ method: 'GET', url: '/api/me' })).statusCode).toBe(401);
    const bad = await app.inject({
      method: 'POST',
      url: '/api/auth/telegram',
      payload: { initData: 'auth_date=1&user=%7B%22id%22%3A1%7D&hash=' + '0'.repeat(64) },
    });
    expect(bad.statusCode).toBe(401);
    expect(bad.json()).toMatchObject({ error: 'INIT_DATA_INVALID' });
  });

  it('never lets concurrent debits overdraw a wallet', async () => {
    const { me } = (await login(tgId + 1)).json();
    const debits = Array.from({ length: 25 }, (_, i) =>
      ctx.ledger
        .post({
          userId: me.id,
          currency: 'CHIPS',
          amount: -1000n,
          type: 'GAME_STAKE',
          source: 'test',
          idempotencyKey: `race:${me.id}:${i}`,
        })
        .then(
          () => 'ok',
          (e: { code?: string }) => e.code,
        ),
    );
    const results = await Promise.all(debits);
    expect(results.filter((r) => r === 'ok')).toHaveLength(10);
    expect(results.filter((r) => r === 'INSUFFICIENT_FUNDS')).toHaveLength(15);
    expect((await ctx.users.wallet(me.id)).chips).toBe(0);
  });

  it('applies a repeated operation only once, even when sent concurrently', async () => {
    const { me } = (await login(tgId + 2)).json();
    const entry = {
      userId: me.id,
      currency: 'CHIPS' as const,
      amount: 500n,
      type: 'GAME_PAYOUT' as const,
      source: 'test',
      idempotencyKey: `payout:${me.id}`,
    };
    const results = await Promise.all(Array.from({ length: 8 }, () => ctx.ledger.post(entry)));
    expect(new Set(results.map((r) => r.transactionId)).size).toBe(1);
    expect((await ctx.users.wallet(me.id)).chips).toBe(10_500);

    const rows = await db.transaction.findMany({ where: { userId: me.id }, orderBy: { createdAt: 'asc' } });
    for (const row of rows) expect(row.balanceAfter).toBe(row.balanceBefore + row.amount);
  });
});
