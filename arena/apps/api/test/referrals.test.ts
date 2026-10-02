import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import type { RoomSettings } from '@arena/shared';
import { buildApp, type AppHandle } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { createContext } from '../src/context.js';
import { createDb, type Db } from '../src/db.js';
import { seedCatalog } from '../src/services/catalog.js';
import { parseReferralParam } from '../src/services/referrals.js';
import { TelegramBot } from '../src/services/notifier.js';
import { signInitData } from '../src/telegram/initData.js';
import { Bot } from './bots.js';

const url = process.env.TEST_DATABASE_URL;
const BOT_TOKEN = '123456:TEST-token-for-referrals';
const OWNER_TG = 880_000_001;
const ROOM: Omit<RoomSettings, 'password'> = {
  stake: 100, players: 2, deckSize: 36, speed: 'fast', variant: 'podkidnoy', throwIn: 'all', fairness: 'fair', ending: 'classic', server: 'almaz', isPrivate: false,
};

interface Player {
  id: string;
  token: string;
  tg: number;
  ws: Bot | null;
}

describe('referral start parameter', () => {
  it('accepts only ref_ with a sane code', () => {
    expect(parseReferralParam('ref_abc234')).toBe('abc234');
    expect(parseReferralParam('ref_')).toBeNull();
    expect(parseReferralParam('ref_ABC!')).toBeNull();
    expect(parseReferralParam('game_x')).toBeNull();
    expect(parseReferralParam(null)).toBeNull();
  });
});

describe.skipIf(!url)('referral program', () => {
  let db: Db;
  let handle: AppHandle;
  let address: string;
  const sent: { chatId: string; text: string }[] = [];
  let nextTg = 700_000_000 + Math.floor(Math.random() * 10_000_000);
  const sockets: Bot[] = [];

  beforeAll(async () => {
    const config = loadConfig({
      NODE_ENV: 'test', DATABASE_URL: url!, BOT_TOKEN, SESSION_SECRET: 'r'.repeat(40), WEB_DIST: '/none',
      BOT_USERNAME: 'maruska_bot', MINI_APP_SHORT_NAME: 'arena', OWNER_IDS: String(OWNER_TG), AUTH_RATE_LIMIT: '100',
    });
    db = createDb(url!);
    await seedCatalog(db);
    await db.setting.deleteMany({ where: { key: 'referral' } });
    const fakeFetch = (async (_url: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      sent.push({ chatId: body.chat_id, text: body.text });
      return new Response('{"ok":true}', { status: 200 });
    }) as typeof fetch;
    handle = await buildApp(createContext(config, db), { bot: new TelegramBot(BOT_TOKEN, 'http://fake', fakeFetch) });
    address = await handle.app.listen({ port: 0, host: '127.0.0.1' });
  });

  afterAll(async () => {
    for (const s of sockets) s.close();
    await db?.setting.deleteMany({ where: { key: 'referral' } });
    await handle?.app.close();
    await db?.$disconnect();
  });

  async function login(tg: number, name: string, startParam?: string) {
    const initData = signInitData(
      {
        auth_date: String(Math.floor(Date.now() / 1000)),
        user: JSON.stringify({ id: tg, first_name: name }),
        ...(startParam ? { start_param: startParam } : {}),
      },
      BOT_TOKEN,
    );
    const res = await handle.app.inject({ method: 'POST', url: '/api/auth/telegram', payload: { initData } });
    expect(res.statusCode).toBe(200);
    return res.json() as { token: string; me: { id: string } };
  }

  async function player(name: string, startParam?: string, online = false, tg = nextTg++): Promise<Player> {
    const { token, me } = await login(tg, name, startParam);
    const p: Player = { id: me.id, token, tg, ws: null };
    if (online) {
      p.ws = new Bot(name, me.id, token, address);
      await p.ws.connect();
      sockets.push(p.ws);
    }
    return p;
  }

  const call = (p: Player, method: 'GET' | 'POST' | 'PUT', path: string, payload?: object) =>
    handle.app.inject({ method, url: `/api${path}`, payload, headers: { authorization: `Bearer ${p.token}` } });

  /** Coins from invites only (achievements pay coins too). */
  const coins = async (p: Player) => {
    const rows = await db.transaction.findMany({ where: { userId: p.id, type: 'REFERRAL' }, select: { amount: true } });
    return rows.reduce((sum, r) => sum + Number(r.amount), 0);
  };

  async function playGame(a: Player, b: Player) {
    const created = (await call(a, 'POST', '/rooms', ROOM)).json();
    const joined = await call(b, 'POST', `/rooms/${created.room.id}/join`, {});
    expect(joined.statusCode, joined.body).toBe(200);
    await a.ws!.send({ type: 'READY', roomId: created.room.id, ready: true });
    await b.ws!.send({ type: 'READY', roomId: created.room.id, ready: true });
    const started = await a.ws!.waitFor((m) => m.type === 'GAME_STARTED');
    if (started.type !== 'GAME_STARTED') throw new Error('unreachable');
    await b.ws!.send({ type: 'LEAVE_GAME', gameId: started.gameId });
    await a.ws!.waitFor((m) => m.type === 'GAME_FINISHED');
    await call(a, 'POST', `/rooms/${created.room.id}/leave`);
    await call(b, 'POST', `/rooms/${created.room.id}/leave`);
  }

  const waitFor = async (check: () => Promise<boolean>) => {
    for (let i = 0; i < 100 && !(await check()); i++) await new Promise((r) => setTimeout(r, 30));
    expect(await check()).toBe(true);
  };

  it('an invite link ties the newcomer, makes friends, and pays both after the first game with a person', async () => {
    const host = await player('Хозяин', undefined, true);
    const info = (await call(host, 'GET', '/referrals')).json();
    expect(info).toMatchObject({ enabled: true, inviteeCoins: 500, referrerCoins: 500, invited: 0 });
    expect(info.link).toMatch(/^https:\/\/t\.me\/maruska_bot\/arena\?startapp=ref_[a-z0-9]{8}$/);
    const param = info.link.split('startapp=')[1];
    // The code stays the same.
    expect((await call(host, 'GET', '/referrals')).json().link).toBe(info.link);

    const guest = await player('Гость', param, true);
    const mine = (await call(guest, 'GET', '/referrals')).json();
    expect(mine.invitedBy).toMatchObject({ id: host.id, pending: true, coins: 500 });
    const friends = (await call(host, 'GET', '/friends')).json();
    expect(friends.map((f: { id: string }) => f.id)).toContain(guest.id);
    expect((await call(host, 'GET', '/referrals')).json()).toMatchObject({ invited: 1, rewarded: 0, earned: 0 });

    const hostBefore = await coins(host);
    const guestBefore = await coins(guest);
    await playGame(host, guest);
    await waitFor(async () => (await coins(guest)) === guestBefore + 500);
    await waitFor(async () => (await coins(host)) === hostBefore + 500);
    await host.ws!.waitFor((m) => m.type === 'REFERRAL_REWARD' && !m.invitee && m.coins === 500);
    await guest.ws!.waitFor((m) => m.type === 'REFERRAL_REWARD' && m.invitee);
    expect((await call(host, 'GET', '/referrals')).json()).toMatchObject({ invited: 1, rewarded: 1, earned: 500 });
    expect((await call(guest, 'GET', '/referrals')).json().invitedBy).toMatchObject({ pending: false, coins: 500 });

    // A second game pays nothing more.
    await playGame(host, guest);
    await new Promise((r) => setTimeout(r, 200));
    expect(await coins(host)).toBe(hostBefore + 500);
    expect(await coins(guest)).toBe(guestBefore + 500);
  });

  it('ignores own code, old accounts, unknown codes and second invites', async () => {
    const host = await player('Хозяин2');
    const param = (await call(host, 'GET', '/referrals')).json().link.split('startapp=')[1];
    // Own link.
    await login(host.tg, 'Хозяин2', param);
    expect((await call(host, 'GET', '/referrals')).json().invitedBy).toBeNull();
    // Unknown code.
    const lost = await player('Потерянный', 'ref_zzzzzzzz');
    expect((await call(lost, 'GET', '/referrals')).json().invitedBy).toBeNull();
    // An account that already played (or is old) cannot be claimed.
    const old = await player('Старожил');
    await db.user.update({ where: { id: old.id }, data: { createdAt: new Date(Date.now() - 3600_000) } });
    await login(old.tg, 'Старожил', param);
    expect((await call(old, 'GET', '/referrals')).json().invitedBy).toBeNull();
    // The first invite wins.
    const other = await player('Другой');
    const otherParam = (await call(other, 'GET', '/referrals')).json().link.split('startapp=')[1];
    const newcomer = await player('Новичок', param);
    await login(newcomer.tg, 'Новичок', otherParam);
    expect((await call(newcomer, 'GET', '/referrals')).json().invitedBy.id).toBe(host.id);
  });

  it('owner settings: amounts and the daily limit for the inviter', async () => {
    const boss = await player('Владелец', undefined, false, OWNER_TG);
    const bad = await call(boss, 'PUT', '/owner/referrals', { enabled: true, inviteeCoins: 10, referrerCoins: 20, dailyLimit: 0 });
    expect(bad.statusCode).toBe(400);
    const ok = await call(boss, 'PUT', '/owner/referrals', { enabled: true, inviteeCoins: 10, referrerCoins: 20, dailyLimit: 1 });
    expect(ok.json()).toMatchObject({ inviteeCoins: 10, referrerCoins: 20, dailyLimit: 1 });

    const host = await player('Зазывала', undefined, true);
    const param = (await call(host, 'GET', '/referrals')).json().link.split('startapp=')[1];
    const one = await player('Первый', param, true);
    const two = await player('Второй', param, true);
    const start = await coins(host);
    const twoStart = await coins(two);
    await playGame(host, one);
    await waitFor(async () => (await coins(host)) === start + 20);
    // Over the limit: the newcomer still gets coins, the inviter does not.
    await playGame(two, one);
    await waitFor(async () => (await coins(two)) === twoStart + 10);
    expect(await coins(host)).toBe(start + 20);
    const list = (await call(host, 'GET', '/referrals')).json().friends;
    expect(list.find((f: { id: string }) => f.id === two.id)).toMatchObject({ coins: 0 });
    expect(list.find((f: { id: string }) => f.id === one.id)).toMatchObject({ coins: 20 });

    // Turned off: new links tie nobody.
    await call(boss, 'PUT', '/owner/referrals', { enabled: false, inviteeCoins: 10, referrerCoins: 20, dailyLimit: 1 });
    const late = await player('Поздний', param);
    expect((await call(late, 'GET', '/referrals')).json().invitedBy).toBeNull();
    // Others may not touch the settings.
    expect((await call(host, 'GET', '/owner/referrals')).statusCode).toBe(403);
  });
});
