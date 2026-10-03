import { LOGIN_REWARDS, QUESTS_BONUS, previousDay, questDay, questsFor, type DailyDto, type QuestGame } from '@arena/shared';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { buildApp, type AppHandle } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { createContext } from '../src/context.js';
import { createDb, type Db } from '../src/db.js';
import { seedCatalog } from '../src/services/catalog.js';
import { signInitData } from '../src/telegram/initData.js';

const url = process.env.TEST_DATABASE_URL;
const BOT_TOKEN = '123456:TEST-token-for-daily';
const DAY = 24 * 3600_000;

describe.skipIf(!url)('daily quests and the login calendar', () => {
  let db: Db;
  let handle: AppHandle;
  let nextTg = 970_000_000 + Math.floor(Math.random() * 10_000_000);

  beforeAll(async () => {
    const config = loadConfig({
      NODE_ENV: 'test', DATABASE_URL: url!, BOT_TOKEN, SESSION_SECRET: 'd'.repeat(40), WEB_DIST: '/none', INTERNAL_API_SECRET: 'internal-secret-123',
    });
    db = createDb(url!);
    await seedCatalog(db);
    handle = await buildApp(createContext(config, db), { bot: null });
  });

  afterAll(async () => {
    await handle?.app.close();
    await db?.$disconnect();
  });

  async function player(): Promise<{ id: string; token: string }> {
    const tg = nextTg++;
    const initData = signInitData({ auth_date: String(Math.floor(Date.now() / 1000)), user: JSON.stringify({ id: tg, first_name: 'Игрок' }) }, BOT_TOKEN);
    const res = await handle.app.inject({ method: 'POST', url: '/api/auth/telegram', payload: { initData }, remoteAddress: `10.7.${tg % 250}.${tg % 200}` });
    const { token, me } = res.json();
    return { id: me.id, token };
  }
  const call = (p: { token: string }, method: 'GET' | 'POST', path: string, payload?: object) =>
    handle.app.inject({ method, url: `/api${path}`, payload, headers: { authorization: `Bearer ${p.token}` } });
  const balance = async (userId: string) => {
    const rows = await db.wallet.findMany({ where: { userId } });
    return { credits: Number(rows.find((w) => w.currency === 'CREDITS')!.balance), coins: Number(rows.find((w) => w.currency === 'COINS')!.balance) };
  };
  const game = (userId: string, g: QuestGame, at = Date.now()) => db.$transaction((tx) => handle.ctx.daily.onGame(tx, userId, g, at));
  const win = (variant: QuestGame['variant']): QuestGame => ({ won: true, stake: 1_000, variant, players: 3, transfers: 1 });

  it('gives three quests a day, one of each tier, the same all day', () => {
    const a = questsFor('user-a', '2026-10-03');
    expect(a).toHaveLength(3);
    expect(questsFor('user-a', '2026-10-03').map((q) => q.key)).toEqual(a.map((q) => q.key));
    expect(previousDay('2026-10-01')).toBe('2026-09-30');
    // 23:30 Moscow is still the same day; 00:10 Moscow is the next one.
    expect(questDay(Date.parse('2026-10-03T20:30:00Z'))).toBe('2026-10-03');
    expect(questDay(Date.parse('2026-10-03T21:10:00Z'))).toBe('2026-10-04');
  });

  it('counts games, pays each finished quest once and the bonus for all three', async () => {
    const p = await player();
    const start = await balance(p.id);
    let daily = (await call(p, 'GET', '/daily')).json() as DailyDto;
    expect(daily.quests).toHaveLength(3);
    expect(daily.quests.every((q) => q.progress === 0 && !q.claimed)).toBe(true);
    expect(daily.bonus.done).toBe(false);

    const first = daily.quests[0]!;
    expect((await call(p, 'POST', '/daily/quests', { day: daily.today, key: first.key })).json().error).toBe('REWARD_NOT_READY');
    expect((await call(p, 'POST', '/daily/quests', { day: daily.today, key: 'all_done' })).json().error).toBe('REWARD_NOT_READY');
    expect((await call(p, 'POST', '/daily/quests', { day: daily.today, key: 'no_such' })).statusCode).toBe(400);

    for (let i = 0; i < 8; i++) {
      await game(p.id, win('podkidnoy'));
      await game(p.id, win('perevodnoy'));
    }
    daily = (await call(p, 'GET', '/daily')).json() as DailyDto;
    expect(daily.quests.every((q) => q.progress === q.goal)).toBe(true);
    expect(daily.bonus.done).toBe(true);
    expect((await call(p, 'GET', '/me')).json().daily.claimable).toBe(5); // 3 quests + bonus + calendar

    let expected = { ...start };
    for (const q of daily.quests) {
      const res = await call(p, 'POST', '/daily/quests', { day: q.day, key: q.key });
      expect(res.statusCode).toBe(200);
      expected = { credits: expected.credits + q.reward.credits, coins: expected.coins + q.reward.coins };
      expect((await call(p, 'POST', '/daily/quests', { day: q.day, key: q.key })).json().error).toBe('REWARD_CLAIMED');
    }
    // Two taps at once on the bonus: one pays.
    const both = await Promise.all([1, 2].map(() => call(p, 'POST', '/daily/quests', { day: daily.today, key: 'all_done' })));
    expect(both.map((r) => r.statusCode).sort()).toEqual([200, 409]);
    expected.coins += QUESTS_BONUS.coins;
    expect(await balance(p.id)).toEqual(expected);
    expect((await call(p, 'GET', '/me')).json().daily.claimable).toBe(1); // the calendar is left
  });

  it('a loss resets «подряд»; a finished quest of yesterday is still collectable today', async () => {
    const p = await player();
    const now = Date.now();
    const day = questDay(now);
    await db.dailyQuest.create({ data: { userId: p.id, day, key: 'win_row_2', progress: 1 } });
    await game(p.id, { ...win('podkidnoy'), won: false }, now);
    const row = await db.dailyQuest.findUnique({ where: { userId_day_key: { userId: p.id, day, key: 'win_row_2' } } });
    // Only today's quests move: win_row_2 is reset only when it is among them.
    const todays = questsFor(p.id, day).some((q) => q.key === 'win_row_2');
    expect(row!.progress).toBe(todays ? 0 : 1);

    const yesterday = previousDay(day);
    const old = questsFor(p.id, yesterday)[0]!;
    await db.dailyQuest.create({ data: { userId: p.id, day: yesterday, key: old.key, progress: old.goal } });
    const daily = (await call(p, 'GET', '/daily')).json() as DailyDto;
    expect(daily.quests.filter((q) => q.day === yesterday).map((q) => q.key)).toEqual([old.key]);
    expect((await call(p, 'POST', '/daily/quests', { day: yesterday, key: old.key })).statusCode).toBe(200);
    expect((await call(p, 'POST', '/daily/quests', { day: previousDay(yesterday), key: old.key })).statusCode).toBe(404);
  });

  it('login calendar: once a day, seven in a row, a missed day starts over', async () => {
    const p = await player();
    const daily = handle.ctx.daily;
    const t0 = Date.parse('2026-10-05T09:00:00Z');
    const before = await balance(p.id);

    let got = (await call(p, 'GET', '/daily')).json() as DailyDto;
    expect(got.calendar).toMatchObject({ step: 1, claimedToday: false, reset: false });
    expect((await call(p, 'POST', '/daily/login')).statusCode).toBe(200);
    expect((await call(p, 'POST', '/daily/login')).json().error).toBe('REWARD_CLAIMED');
    got = (await call(p, 'GET', '/daily')).json() as DailyDto;
    expect(got.calendar).toMatchObject({ step: 1, claimedToday: true });
    await db.profile.update({ where: { userId: p.id }, data: { loginDay: null, loginStep: 0 } });

    for (let i = 0; i < 7; i++) expect((await daily.claimLogin(p.id, t0 + i * DAY)).calendar).toMatchObject({ step: i + 1, claimedToday: true });
    // After the chest the week starts again.
    expect((await daily.get(p.id, t0 + 7 * DAY)).calendar).toMatchObject({ step: 1, reset: false });
    expect((await daily.claimLogin(p.id, t0 + 7 * DAY)).calendar.step).toBe(1);
    expect((await daily.claimLogin(p.id, t0 + 8 * DAY)).calendar.step).toBe(2);
    // A day missed: back to the first reward, and the screen says why.
    expect((await daily.get(p.id, t0 + 10 * DAY)).calendar).toMatchObject({ step: 1, reset: true });

    const sum = [...LOGIN_REWARDS, LOGIN_REWARDS[0]!, LOGIN_REWARDS[1]!, LOGIN_REWARDS[0]!].reduce(
      (acc, r) => ({ credits: acc.credits + r.credits, coins: acc.coins + r.coins }),
      { credits: 0, coins: 0 },
    );
    expect(await balance(p.id)).toEqual({ credits: before.credits + sum.credits, coins: before.coins + sum.coins });
  });
});
