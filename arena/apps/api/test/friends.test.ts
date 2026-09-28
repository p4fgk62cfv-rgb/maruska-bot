import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import type { RoomSettings } from '@arena/shared';
import { buildApp, type AppHandle } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { createContext } from '../src/context.js';
import { createDb, type Db } from '../src/db.js';
import { seedCatalog } from '../src/services/catalog.js';
import { TelegramBot } from '../src/services/notifier.js';
import { signInitData } from '../src/telegram/initData.js';
import { Bot } from './bots.js';

const url = process.env.TEST_DATABASE_URL;
const BOT_TOKEN = '123456:TEST-token-for-friends';
const ROOM: Omit<RoomSettings, 'password'> = {
  stake: 100, players: 2, deckSize: 36, speed: 'fast', variant: 'podkidnoy', throwIn: 'all', fairness: 'fair', ending: 'classic', server: 'almaz', isPrivate: false,
};

interface Player {
  id: string;
  token: string;
  tg: number;
  ws: Bot | null;
}

describe.skipIf(!url)('friends, requests and invites', () => {
  let db: Db;
  let handle: AppHandle;
  let address: string;
  const sent: { chatId: string; text: string; url?: string }[] = [];
  let nextTg = 900_000_000 + Math.floor(Math.random() * 10_000_000);
  const sockets: Bot[] = [];

  beforeAll(async () => {
    const config = loadConfig({
      NODE_ENV: 'test', DATABASE_URL: url!, BOT_TOKEN, SESSION_SECRET: 'f'.repeat(40), WEB_DIST: '/none',
      BOT_USERNAME: 'maruska_bot', MINI_APP_SHORT_NAME: 'arena', INTERNAL_API_SECRET: 'internal-secret-123',
    });
    db = createDb(url!);
    await seedCatalog(db);
    // Fake Telegram: records what the bot would have sent.
    const fakeFetch = (async (_url: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      sent.push({ chatId: body.chat_id, text: body.text, url: body.reply_markup?.inline_keyboard?.[0]?.[0]?.url });
      return new Response('{"ok":true}', { status: 200 });
    }) as typeof fetch;
    handle = await buildApp(createContext(config, db), { bot: new TelegramBot(BOT_TOKEN, 'http://fake', fakeFetch) });
    address = await handle.app.listen({ port: 0, host: '127.0.0.1' });
  });

  afterAll(async () => {
    for (const s of sockets) s.close();
    await handle?.app.close();
    await db?.$disconnect();
  });

  async function player(name: string, username?: string, online = false): Promise<Player> {
    const tg = nextTg++;
    const initData = signInitData(
      { auth_date: String(Math.floor(Date.now() / 1000)), user: JSON.stringify({ id: tg, first_name: name, username }) },
      BOT_TOKEN,
    );
    const res = await handle.app.inject({ method: 'POST', url: '/api/auth/telegram', payload: { initData }, remoteAddress: `10.1.${tg % 250}.${tg % 200}` });
    const { token, me } = res.json();
    const p: Player = { id: me.id, token, tg, ws: null };
    if (online) {
      p.ws = new Bot(name, me.id, token, address);
      await p.ws.connect();
      sockets.push(p.ws);
    }
    return p;
  }

  const call = (p: Player, method: 'GET' | 'POST' | 'DELETE', path: string, payload?: object) =>
    handle.app.inject({ method, url: `/api${path}`, payload, headers: { authorization: `Bearer ${p.token}` } });

  const waitSent = async (chatId: number, contains = '') => {
    const match = (s: (typeof sent)[number]) => s.chatId === String(chatId) && s.text.includes(contains);
    for (let i = 0; i < 50 && !sent.some(match); i++) await new Promise((r) => setTimeout(r, 20));
    return sent.find(match);
  };

  it('a request to an offline player goes out as a bot message; accepting makes both friends', async () => {
    const a = await player('Анна', undefined, true);
    const b = await player('Борис');
    expect((await call(a, 'POST', '/friends/requests', { userId: b.id })).json()).toEqual({ status: 'sent' });
    expect((await call(a, 'POST', '/friends/requests', { userId: b.id })).json()).toEqual({ status: 'already_sent' });

    const msg = await waitSent(b.tg);
    expect(msg?.text).toContain('Анна');
    expect(msg?.url).toBe('https://t.me/maruska_bot/arena?startapp=friends');

    const { incoming } = (await call(b, 'GET', '/friends/requests')).json();
    expect(incoming).toHaveLength(1);
    expect((await call(b, 'POST', `/friends/requests/${incoming[0].id}/accept`)).statusCode).toBe(200);
    await a.ws!.waitFor((m) => m.type === 'FRIEND_ACCEPTED' && m.friend.id === b.id);

    const listA = (await call(a, 'GET', '/friends')).json();
    const listB = (await call(b, 'GET', '/friends')).json();
    expect(listA.map((f: { id: string }) => f.id)).toEqual([b.id]);
    expect(listB[0]).toMatchObject({ id: a.id, presence: 'online' });

    expect((await call(a, 'DELETE', `/friends/${b.id}`)).statusCode).toBe(200);
    expect((await call(b, 'GET', '/friends')).json()).toEqual([]);
  });

  it('online players get the request instantly; asking back accepts it; decline and cancel work', async () => {
    const a = await player('Вера');
    const b = await player('Глеб', undefined, true);
    await call(a, 'POST', '/friends/requests', { userId: b.id });
    await b.ws!.waitFor((m) => m.type === 'FRIEND_REQUEST' && m.from.id === a.id);
    expect((await call(b, 'POST', '/friends/requests', { userId: a.id })).json()).toEqual({ status: 'friends' });
    expect((await call(a, 'GET', '/friends')).json()).toHaveLength(1);

    const c = await player('Дина');
    await call(a, 'POST', '/friends/requests', { userId: c.id });
    const out = (await call(a, 'GET', '/friends/requests')).json().outgoing;
    expect((await call(a, 'DELETE', `/friends/requests/${out[0].id}`)).statusCode).toBe(200);
    expect((await call(c, 'GET', '/friends/requests')).json().incoming).toEqual([]);

    await call(c, 'POST', '/friends/requests', { userId: a.id });
    const inc = (await call(a, 'GET', '/friends/requests')).json().incoming;
    expect((await call(a, 'POST', `/friends/requests/${inc[0].id}/decline`)).statusCode).toBe(200);
    // Nobody else may accept or cancel a request that is not theirs.
    expect((await call(c, 'POST', `/friends/requests/${inc[0].id}/accept`)).statusCode).toBe(404);
  });

  it('finds players by @username and shows the relation', async () => {
    const tag = `durak${Math.floor(Math.random() * 1e6)}`;
    const a = await player('Егор', `${tag}_a`);
    const b = await player('Жанна', `${tag}_b`);
    await call(a, 'POST', '/friends/requests', { userId: b.id });
    const found = (await call(a, 'GET', `/users/search?q=@${tag}`)).json();
    expect(found).toEqual([expect.objectContaining({ id: b.id, relation: 'outgoing' })]);
    expect((await call(a, 'GET', '/users/search?q=du')).json()).toEqual([]);
  });

  it('invites a friend to my table: instantly when online, by bot link when away', async () => {
    const host = await player('Зоя', undefined, true);
    const online = await player('Игорь', undefined, true);
    const away = await player('Кира');
    const stranger = await player('Лев');
    for (const f of [online, away]) {
      await call(host, 'POST', '/friends/requests', { userId: f.id });
      const inc = (await call(f, 'GET', '/friends/requests')).json().incoming;
      await call(f, 'POST', `/friends/requests/${inc[0].id}/accept`);
    }
    expect((await call(host, 'POST', `/friends/${online.id}/invite`)).json()).toMatchObject({ error: 'NOT_IN_ROOM' });

    const created = (await call(host, 'POST', '/rooms', { ...ROOM, isPrivate: true, password: 'pw', players: 3 })).json();
    expect((await call(host, 'POST', `/friends/${stranger.id}/invite`)).json()).toMatchObject({ error: 'NOT_FRIENDS' });

    expect((await call(host, 'POST', `/friends/${online.id}/invite`)).statusCode).toBe(200);
    const invite = await online.ws!.waitFor((m) => m.type === 'ROOM_INVITE');
    if (invite.type !== 'ROOM_INVITE') throw new Error('unreachable');
    expect(invite.room.id).toBe(created.room.id);
    expect((await call(online, 'POST', `/rooms/${created.room.id}/join`, { invite: invite.invite })).statusCode).toBe(200);
    expect((await call(host, 'POST', `/friends/${online.id}/invite`)).json()).toMatchObject({ error: 'RATE_LIMITED' });

    expect((await call(host, 'POST', `/friends/${away.id}/invite`)).statusCode).toBe(200);
    const msg = await waitSent(away.tg, 'зовёт');
    expect(msg?.url).toMatch(new RegExp(`^https://t.me/maruska_bot/arena\\?startapp=game_${created.room.id}_`));
  });

  it('lists recent opponents after a game', async () => {
    const a = await player('Мира', undefined, true);
    const b = await player('Нил', undefined, true);
    const room = (await call(a, 'POST', '/rooms', ROOM)).json().room;
    await call(b, 'POST', `/rooms/${room.id}/join`, {});
    await a.ws!.send({ type: 'READY', roomId: room.id, ready: true });
    await b.ws!.send({ type: 'READY', roomId: room.id, ready: true });
    const started = await a.ws!.waitFor((m) => m.type === 'GAME_STARTED');
    if (started.type !== 'GAME_STARTED') throw new Error('unreachable');
    await b.ws!.send({ type: 'LEAVE_GAME', gameId: started.gameId });
    await a.ws!.waitFor((m) => m.type === 'GAME_FINISHED');

    const recent = (await call(a, 'GET', '/friends/recent')).json();
    expect(recent[0]).toMatchObject({ id: b.id, relation: 'none', games: 1 });
  });

  it('five friends unlock «Компания» with its coin reward', async () => {
    const me = await player('Олег');
    for (let i = 0; i < 5; i++) {
      const f = await player(`Друг ${i}`);
      await call(f, 'POST', '/friends/requests', { userId: me.id });
      await call(me, 'POST', '/friends/requests', { userId: f.id });
    }
    const achievements = (await call(me, 'GET', '/achievements')).json();
    expect(achievements.find((a: { key: string }) => a.key === 'social_5').unlockedAt).not.toBeNull();
    expect((await call(me, 'GET', '/me')).json().wallet.coins).toBe(15);
  });

  it('internal API answers the bot only with the shared secret', async () => {
    const p = await player('Пётр');
    expect((await handle.app.inject({ method: 'GET', url: `/api/internal/players/${p.tg}` })).statusCode).toBe(401);
    const res = await handle.app.inject({
      method: 'GET',
      url: `/api/internal/players/${p.tg}`,
      headers: { authorization: 'Bearer internal-secret-123' },
    });
    expect(res.json()).toMatchObject({ rating: 0, league: 'Серебряная', gamesPlayed: 0 });
  });

  it('items: buy once for coins, equip one per kind, others see the frame at the table', async () => {
    const buyer = await player('Рита');
    expect((await call(buyer, 'POST', '/items/frame_silver/buy')).json()).toMatchObject({ error: 'INSUFFICIENT_FUNDS' });
    expect((await call(buyer, 'POST', '/items/frame_silver/equip')).json()).toMatchObject({ error: 'FORBIDDEN' });

    await db.$transaction((tx) =>
      handle.ctx.ledger.postIn(tx, { userId: buyer.id, currency: 'COINS', amount: 100n, type: 'ADMIN', source: 'test', idempotencyKey: `coins:${buyer.id}` }),
    );
    const results = await Promise.all([1, 2, 3].map(() => call(buyer, 'POST', '/items/frame_silver/buy')));
    expect(results.map((r) => r.statusCode)).toEqual([200, 200, 200]);
    expect((await call(buyer, 'GET', '/me')).json().wallet.coins).toBe(40);

    expect((await call(buyer, 'POST', '/items/frame_silver/equip')).json()).toMatchObject({ frame: 'frame_silver', cardBack: 'back_classic' });
    // Illustrated backs cost credits: 1450 at sign-up is not enough for 2500.
    expect((await call(buyer, 'POST', '/items/back_tartan/buy')).json()).toMatchObject({ error: 'INSUFFICIENT_FUNDS' });
    await db.$transaction((tx) =>
      handle.ctx.ledger.postIn(tx, { userId: buyer.id, currency: 'CREDITS', amount: 2_000n, type: 'ADMIN', source: 'test', idempotencyKey: `credits:${buyer.id}` }),
    );
    expect((await call(buyer, 'POST', '/items/back_tartan/buy')).statusCode).toBe(200);
    expect((await call(buyer, 'GET', '/me')).json().wallet).toMatchObject({ credits: 950, coins: 40 });
    expect((await call(buyer, 'POST', '/items/back_tartan/equip')).json()).toMatchObject({ cardBack: 'back_tartan' });
    const items = (await call(buyer, 'GET', '/items')).json() as { key: string; kind: string; equipped: boolean }[];
    expect(items.filter((i) => i.equipped).map((i) => i.key).sort()).toEqual(['back_tartan', 'frame_silver']);
    // The table is no longer sold: one felt for everyone.
    expect(items.some((i) => i.kind === 'TABLE')).toBe(false);
    expect((await call(buyer, 'POST', '/items/table_midnight/buy')).json()).toMatchObject({ error: 'NOT_FOUND' });

    const room = (await call(buyer, 'POST', '/rooms', ROOM)).json().room;
    expect(room.seats[0]).toMatchObject({ frame: 'frame_silver', crown: null });
    await call(buyer, 'POST', `/rooms/${room.id}/leave`);
    expect((await call(buyer, 'POST', '/items/frame_silver/unequip')).json()).toMatchObject({ frame: null });
  });

  it('refunds items taken off sale once, however many times the catalogue is seeded', async () => {
    const owner = await player('Владелец стола');
    const midnight = await db.item.findUniqueOrThrow({ where: { key: 'table_midnight' } });
    await db.userItem.create({ data: { userId: owner.id, itemId: midnight.id, source: 'shop', equipped: true } });
    const before = (await call(owner, 'GET', '/me')).json().wallet.coins as number;
    await seedCatalog(db);
    await seedCatalog(db);
    expect((await call(owner, 'GET', '/me')).json().wallet.coins).toBe(before + 80);
    expect(await db.userItem.count({ where: { userId: owner.id, itemId: midnight.id } })).toBe(0);
  });
});
