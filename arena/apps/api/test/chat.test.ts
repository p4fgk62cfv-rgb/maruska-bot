import type { ChatMessageDto, ChatStateDto } from '@arena/shared';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { buildApp, type AppHandle } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { createContext } from '../src/context.js';
import { createDb, type Db } from '../src/db.js';
import { seedCatalog } from '../src/services/catalog.js';
import { signInitData } from '../src/telegram/initData.js';
import { Bot } from './bots.js';

const url = process.env.TEST_DATABASE_URL;
const BOT_TOKEN = '123456:TEST-token-for-chat';
const OWNER_TG = 990_000_001;

describe.skipIf(!url)('the common chat', () => {
  let db: Db;
  let handle: AppHandle;
  let address: string;
  let nextTg = 980_000_000 + Math.floor(Math.random() * 9_000_000);
  const sockets: Bot[] = [];

  beforeAll(async () => {
    const config = loadConfig({
      NODE_ENV: 'test', DATABASE_URL: url!, BOT_TOKEN, SESSION_SECRET: 'c'.repeat(40), WEB_DIST: '/none', INTERNAL_API_SECRET: 'internal-secret-123',
      OWNER_IDS: String(OWNER_TG),
    });
    db = createDb(url!);
    await seedCatalog(db);
    handle = await buildApp(createContext(config, db), { bot: null });
    address = await handle.app.listen({ port: 0, host: '127.0.0.1' });
  });

  afterAll(async () => {
    for (const s of sockets) s.close();
    await handle?.app.close();
    await db?.$disconnect();
  });

  async function player(opts: { games?: number; tg?: number } = {}): Promise<{ id: string; token: string }> {
    const tg = opts.tg ?? nextTg++;
    const initData = signInitData({ auth_date: String(Math.floor(Date.now() / 1000)), user: JSON.stringify({ id: tg, first_name: `Игрок${tg % 1000}` }) }, BOT_TOKEN);
    const res = await handle.app.inject({ method: 'POST', url: '/api/auth/telegram', payload: { initData }, remoteAddress: `10.9.${tg % 250}.${tg % 200}` });
    const { token, me } = res.json();
    await db.profile.update({ where: { userId: me.id }, data: { gamesPlayed: opts.games ?? 1, chatMutedUntil: null } });
    return { id: me.id, token };
  }
  const call = (p: { token: string }, method: 'GET' | 'POST' | 'DELETE', path: string, payload?: object) =>
    handle.app.inject({ method, url: `/api${path}`, payload, headers: { authorization: `Bearer ${p.token}` } });
  const say = (p: { token: string }, text: string) => call(p, 'POST', '/chat', { text });
  async function socket(p: { id: string; token: string }): Promise<Bot> {
    const bot = new Bot(`chat-${p.id.slice(-4)}`, p.id, p.token, address);
    await bot.connect();
    sockets.push(bot);
    return bot;
  }
  const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

  it('a message reaches those who have the chat open, masked; history pages back', async () => {
    const [a, b, c] = [await player(), await player(), await player()];
    const [sb, sc] = [await socket(b), await socket(c)];
    expect((await sb.send({ type: 'CHAT_SUBSCRIBE' })).type).toBe('ACK');

    const res = await say(a, '  привет,   ну ты и сука  ');
    expect(res.statusCode).toBe(200);
    const sent = res.json() as ChatMessageDto;
    expect(sent.text).toBe('привет, ну ты и ***');
    expect(sent.user.id).toBe(a.id);
    const pushed = await sb.waitFor((m) => m.type === 'CHAT_MESSAGE' && m.message.id === sent.id);
    expect(pushed).toMatchObject({ message: { text: 'привет, ну ты и ***' } });
    await pause(200);
    expect(sc.inbox.some((m) => m.type === 'CHAT_MESSAGE')).toBe(false); // chat not open

    const state = (await call(b, 'GET', '/chat')).json() as ChatStateDto;
    expect(state.messages.at(-1)!.id).toBe(sent.id);
    expect(state).toMatchObject({ blocked: null, moderator: false });
    const older = (await call(b, 'GET', `/chat?before=${sent.id}`)).json() as ChatStateDto;
    expect(older.messages.some((m) => m.id === sent.id)).toBe(false);

    expect((await sb.send({ type: 'CHAT_UNSUBSCRIBE' })).type).toBe('ACK');
    const after = (await say(c, 'а теперь не видно')).json() as ChatMessageDto;
    await pause(200);
    expect(sb.inbox.some((m) => m.type === 'CHAT_MESSAGE' && m.message.id === after.id)).toBe(false);
  });

  it('refuses links, newcomers without a game, floods and empty text', async () => {
    const [a, fresh] = [await player(), await player({ games: 0 })];
    expect((await say(a, 'заходи на casino-win.ru')).json().error).toBe('CHAT_LINKS');
    expect((await say(a, 'https://t.me/spam')).json().error).toBe('CHAT_LINKS');
    expect((await say(fresh, 'привет')).json().error).toBe('CHAT_NEED_GAME');
    expect((await call(fresh, 'GET', '/chat')).json().blocked).toEqual({ reason: 'games', until: null });
    expect((await say(a, '   ')).statusCode).toBe(400);
    expect((await say(a, 'x'.repeat(301))).statusCode).toBe(400);
    expect((await say(a, 'раз')).statusCode).toBe(200);
    expect((await say(a, 'два')).json().error).toBe('CHAT_TOO_FAST');
  });

  it('three reports hide a message; the owners are told once', async () => {
    const [author, r1, r2, r3] = [await player(), await player(), await player(), await player()];
    const watcher = await socket(r3);
    await watcher.send({ type: 'CHAT_SUBSCRIBE' });
    const msg = (await say(author, 'неприятное сообщение')).json() as ChatMessageDto;

    expect((await call(author, 'POST', `/chat/${msg.id}/report`)).statusCode).toBe(400); // not your own
    await call(r1, 'POST', `/chat/${msg.id}/report`);
    await call(r1, 'POST', `/chat/${msg.id}/report`); // a repeat does not count
    await call(r2, 'POST', `/chat/${msg.id}/report`);
    expect(await db.chatMessage.findUniqueOrThrow({ where: { id: msg.id } })).toMatchObject({ deletedAt: null });
    await call(r3, 'POST', `/chat/${msg.id}/report`);
    expect((await db.chatMessage.findUniqueOrThrow({ where: { id: msg.id } })).deletedAt).not.toBeNull();
    await watcher.waitFor((m) => m.type === 'CHAT_DELETED' && m.ids.includes(msg.id));
    expect((await call(r1, 'GET', '/chat')).json().messages.some((m: ChatMessageDto) => m.id === msg.id)).toBe(false);
  });

  it('the owner deletes messages and mutes a player; the player sees why', async () => {
    const owner = await player({ tg: OWNER_TG });
    const [rude, other] = [await player(), await player()];
    const first = (await say(rude, 'первое')).json() as ChatMessageDto;
    await pause(2100);
    const second = (await say(rude, 'второе')).json() as ChatMessageDto;

    expect((await call(other, 'DELETE', `/chat/${first.id}`)).statusCode).toBe(403);
    expect((await call(other, 'POST', '/chat/mute', { userId: rude.id, hours: 1 })).statusCode).toBe(403);
    expect((await call(owner, 'GET', '/chat')).json()).toMatchObject({ moderator: true, blocked: null });

    expect((await call(owner, 'DELETE', `/chat/${first.id}`)).statusCode).toBe(200);
    const muted = await call(owner, 'POST', '/chat/mute', { userId: rude.id, hours: 24, purge: true });
    expect(muted.json().until).toBeTruthy();
    expect(await db.chatMessage.count({ where: { id: { in: [first.id, second.id] }, deletedAt: null } })).toBe(0);
    expect((await say(rude, 'я снова тут')).json().error).toBe('CHAT_MUTED');
    expect((await call(rude, 'GET', '/chat')).json().blocked).toMatchObject({ reason: 'muted' });

    // A report now reaches the owner through the bot.
    const msg = (await say(other, 'ещё одно неприятное')).json() as ChatMessageDto;
    await call(owner, 'POST', `/chat/${msg.id}/report`);
    expect(await db.notification.count({ where: { userId: owner.id, kind: 'chat_report' } })).toBeGreaterThan(0);

    expect((await call(owner, 'POST', '/chat/mute', { userId: rude.id, hours: 0 })).json().until).toBeNull();
    await pause(2100);
    expect((await say(rude, 'исправился')).statusCode).toBe(200);
    // The owner writes without the game requirement and without being muted.
    expect((await say(owner, 'Правила чата: без мата и рекламы')).statusCode).toBe(200);
  });

  it('old messages are deleted; /me knows the newest message time', async () => {
    const a = await player();
    const old = await db.chatMessage.create({ data: { userId: a.id, text: 'давнее', createdAt: new Date(Date.now() - 8 * 24 * 3600_000) } });
    expect(await handle.ctx.chat.cleanup()).toBeGreaterThanOrEqual(1);
    expect(await db.chatMessage.findUnique({ where: { id: old.id } })).toBeNull();
    const msg = (await say(a, 'свежее')).json() as ChatMessageDto;
    expect((await call(a, 'GET', '/me')).json().chatLastAt).toBe(msg.createdAt);
  });
});
