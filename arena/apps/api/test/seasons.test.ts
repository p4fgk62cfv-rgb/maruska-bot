import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { buildApp, type AppHandle } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { createContext } from '../src/context.js';
import { createDb, type Db } from '../src/db.js';
import { seedCatalog } from '../src/services/catalog.js';
import { moscowMonth, parsePlaces, SeasonService } from '../src/services/seasons.js';
import { autoTournamentPlans } from '../src/services/tournaments.js';
import { signInitData } from '../src/telegram/initData.js';

describe('season and tournament schedule (pure)', () => {
  it('parses prize lists', () => {
    expect(parsePlaces('100000,50000,25000,10000x7')).toEqual([100000, 50000, 25000, 10000, 10000, 10000, 10000, 10000, 10000, 10000]);
    expect(parsePlaces('7,3,1')).toEqual([7, 3, 1]);
    expect(parsePlaces('')).toEqual([]);
    expect(parsePlaces('abc, 5, -3, 2x0, 1x2')).toEqual([5, 1, 1]);
  });

  it('finds the Moscow month', () => {
    // 31 Oct 22:30 UTC is already 1 Nov in Moscow
    const m = moscowMonth(new Date('2026-10-31T22:30:00Z'));
    expect(m.title).toBe('Ноябрь 2026');
    expect(m.start.toISOString()).toBe('2026-10-31T21:00:00.000Z');
    expect(m.end.toISOString()).toBe('2026-11-30T21:00:00.000Z');
  });

  it('plans the next evening and Saturday tournaments', () => {
    const config = { DAILY_TOURNAMENT_HOUR: 20, DAILY_TOURNAMENT_PRIZE: 10_000, WEEKEND_TOURNAMENT_FEE: 1_000, WEEKEND_TOURNAMENT_PRIZE: 50_000 };
    // Friday 17 Oct 2026, 15:00 Moscow
    const [daily, weekend] = autoTournamentPlans(new Date('2026-10-17T12:00:00Z'), config);
    expect(daily!.startsAt.toISOString()).toBe('2026-10-17T17:00:00.000Z'); // 20:00 MSK the same day
    expect(daily!.entryFee).toBe(0);
    expect(daily!.guarantee).toBe(10_000);
    expect(weekend!.startsAt.toISOString()).toBe('2026-10-17T15:00:00.000Z'); // 17 Oct 2026 is a Saturday, 18:00 MSK
    // After 20:00 the next evening one is tomorrow
    const [later] = autoTournamentPlans(new Date('2026-10-17T17:30:00Z'), config);
    expect(later!.startsAt.toISOString()).toBe('2026-10-18T17:00:00.000Z');
    // After Saturday 18:00 the weekend one moves a week ahead
    const [, nextWeek] = autoTournamentPlans(new Date('2026-10-17T15:00:01Z'), config);
    expect(nextWeek!.startsAt.toISOString()).toBe('2026-10-24T15:00:00.000Z');
  });
});

const url = process.env.TEST_DATABASE_URL;
const BOT_TOKEN = '123456:TEST-token-for-seasons';

describe.skipIf(!url)('seasons and auto tournaments (database)', () => {
  let db: Db;
  let handle: AppHandle;
  let nextTg = 970_000_000 + Math.floor(Math.random() * 10_000_000);

  beforeAll(async () => {
    const config = loadConfig({
      NODE_ENV: 'test', DATABASE_URL: url!, BOT_TOKEN, SESSION_SECRET: 's'.repeat(40), WEB_DIST: '/none',
      INTERNAL_API_SECRET: 'internal-secret-789', SEASON_PRIZES: '3000,2000,1000', SEASON_VIP_DAYS: '5',
    });
    db = createDb(url!);
    await seedCatalog(db);
    handle = await buildApp(createContext(config, db), { bot: null });
  });

  afterAll(async () => {
    await handle?.app.close();
    await db?.$disconnect();
  });

  async function player(name: string): Promise<string> {
    const tg = nextTg++;
    const initData = signInitData({ auth_date: String(Math.floor(Date.now() / 1000)), user: JSON.stringify({ id: tg, first_name: name }) }, BOT_TOKEN);
    const res = await handle.app.inject({ method: 'POST', url: '/api/auth/telegram', payload: { initData }, remoteAddress: `10.3.${tg % 250}.${tg % 200}` });
    return res.json().me.id as string;
  }

  const credits = async (userId: string) =>
    (await db.wallet.findUniqueOrThrow({ where: { userId_currency: { userId, currency: 'CREDITS' } } })).balance;

  function service(): SeasonService {
    const ctx = handle.ctx;
    return new SeasonService({ config: ctx.config, db, ledger: ctx.ledger, outbox: ctx.outbox, log: handle.app.log });
  }

  it('pays the top of an ended season once, with VIP for the first place', async () => {
    const [a, b, c, d] = [await player('Аня'), await player('Боря'), await player('Вика'), await player('Гоша')];
    const season = await db.season.create({
      data: { title: `Тест ${Date.now()}`, startsAt: new Date('2020-01-01T00:00:00Z'), endsAt: new Date('2020-02-01T00:00:00Z') },
    });
    await db.seasonRating.createMany({
      data: [
        { seasonId: season.id, userId: a, rating: 50, wins: 5 },
        { seasonId: season.id, userId: b, rating: 80, wins: 8 },
        { seasonId: season.id, userId: c, rating: 50, wins: 7 }, // same rating as Аня, more wins
        { seasonId: season.id, userId: d, rating: 0, wins: 0 }, // nothing earned: no prize
      ],
    });
    const before = { a: await credits(a), b: await credits(b), c: await credits(c), d: await credits(d) };

    expect(await service().pay(season)).toBe(3);
    expect((await credits(b)) - before.b).toBe(3000n);
    expect((await credits(c)) - before.c).toBe(2000n);
    expect((await credits(a)) - before.a).toBe(1000n);
    expect(await credits(d)).toBe(before.d);
    const vip = await db.profile.findUniqueOrThrow({ where: { userId: b } });
    expect(vip.premiumUntil!.getTime()).toBeGreaterThan(Date.now() + 4 * 86_400_000);
    expect((await db.season.findUniqueOrThrow({ where: { id: season.id } })).rewarded).toBe(true);
    expect(await db.notification.count({ where: { userId: b, kind: 'season_reward' } })).toBe(1);

    // A second run (restart, second server) pays nothing
    expect(await service().pay(season)).toBe(0);
    expect((await credits(b)) - before.b).toBe(3000n);
  });

  it('starts the current month when no season covers today, but never on top of an existing one', async () => {
    const svc = service();
    const now = new Date();
    const existing = await db.season.findFirst({ where: { startsAt: { lte: now }, endsAt: { gt: now } } });
    if (!existing) {
      const created = await svc.ensureCurrent(now);
      expect(created).not.toBeNull();
      expect(created!.title).toBe(`Сезон «${moscowMonth(now).title}»`);
    }
    expect(await svc.ensureCurrent(now)).toBeNull();
    expect(await db.season.count({ where: { startsAt: { lte: now }, endsAt: { gt: now } } })).toBe(1);
  });

  it('announces the evening and weekend tournaments once, with the guaranteed pool', async () => {
    const plans = autoTournamentPlans(new Date(), handle.ctx.config);
    await handle.ctx.tournaments.tick();
    await handle.ctx.tournaments.tick();
    for (const plan of plans) {
      const rows = await db.tournament.findMany({ where: { title: plan.title, startsAt: plan.startsAt } });
      expect(rows).toHaveLength(1);
      expect(rows[0]!.status).toBe('REGISTRATION');
      expect(rows[0]!.prizePool).toBe(BigInt(plan.guarantee));
      expect(rows[0]!.entryFee).toBe(BigInt(plan.entryFee));
    }
  });
});
