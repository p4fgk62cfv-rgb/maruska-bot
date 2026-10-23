import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { buildApp, type AppHandle } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { createContext } from '../src/context.js';
import { createDb, type Db } from '../src/db.js';
import { seedCatalog } from '../src/services/catalog.js';
import type { BotMessage, TelegramBot } from '../src/services/notifier.js';
import { signInitData } from '../src/telegram/initData.js';
import { Bot } from './bots.js';

const url = process.env.TEST_DATABASE_URL;
const BOT_TOKEN = '123456:TEST-token-for-mini-tournaments';
const SECRET = 'internal-secret-mini';

interface Player {
  id: string;
  tg: number;
  name: string;
  token: string;
  ws: Bot;
}

describe.skipIf(!url)('mini-tournaments (one knockout table)', () => {
  let db: Db;
  let handle: AppHandle;
  let address: string;
  const sockets: Bot[] = [];
  const sent: { chatId: bigint; message: BotMessage }[] = [];
  let nextTg = 970_000_000 + Math.floor(Math.random() * 10_000_000);
  const chatBase = -1_009_000_000_000 - Math.floor(Math.random() * 1_000_000);
  let chatSeq = 0;

  beforeAll(async () => {
    const config = loadConfig({
      NODE_ENV: 'test', DATABASE_URL: url!, BOT_TOKEN, SESSION_SECRET: 'm'.repeat(40), WEB_DIST: '/none',
      INTERNAL_API_SECRET: SECRET, MINI_TOURNAMENT_READY_SECONDS: '1', BOT_USERNAME: 'BotMaruska_bot', MINI_APP_SHORT_NAME: 'play',
    });
    db = createDb(url!);
    await seedCatalog(db);
    const bot = {
      send: async (chatId: bigint, message: BotMessage) => {
        sent.push({ chatId, message });
        return 'ok' as const;
      },
    } as unknown as TelegramBot;
    handle = await buildApp(createContext(config, db), { bot });
    address = await handle.app.listen({ port: 0, host: '127.0.0.1' });
  });

  afterAll(async () => {
    for (const s of sockets) s.close();
    await handle?.app.close();
    await db?.$disconnect();
  });

  async function player(name: string): Promise<Player> {
    const tg = nextTg++;
    const initData = signInitData({ auth_date: String(Math.floor(Date.now() / 1000)), user: JSON.stringify({ id: tg, first_name: name }) }, BOT_TOKEN);
    const res = await handle.app.inject({ method: 'POST', url: '/api/auth/telegram', payload: { initData }, remoteAddress: `10.7.${tg % 250}.${tg % 200}` });
    const { token, me } = res.json();
    const ws = new Bot(name, me.id, token, address);
    await ws.connect();
    sockets.push(ws);
    return { id: me.id, tg, name, token, ws };
  }

  const internal = (method: 'GET' | 'POST', path: string, payload?: object) =>
    handle.app.inject({ method, url: `/api${path}`, headers: { authorization: `Bearer ${SECRET}` }, ...(payload ? { payload } : {}) });

  const until = async (check: () => Promise<boolean> | boolean, ms = 8000) => {
    const end = Date.now() + ms;
    while (Date.now() < end) {
      if (await check()) return;
      await new Promise((r) => setTimeout(r, 50));
    }
    throw new Error('timed out');
  };

  const said = (chatId: bigint) => sent.filter((m) => m.chatId === chatId).map((m) => m.message.text);

  /** Ссылка последнего стола в группе — и id комнаты из неё. */
  const lastTable = (chatId: bigint) => {
    const msg = [...sent].reverse().find((m) => m.chatId === chatId && m.message.button);
    const link = msg && 'url' in msg.message.button! ? msg.message.button.url : '';
    return { link, roomId: /game_([A-Z0-9]{8})/.exec(link)?.[1] ?? '' };
  };

  const join = (p: Player, roomId: string) =>
    handle.app.inject({ method: 'POST', url: `/api/rooms/${roomId}/join`, headers: { authorization: `Bearer ${p.token}` }, payload: {} });

  async function start(players: Player[], prize = 5000): Promise<{ chatId: bigint; organizer: number }> {
    const chatId = BigInt(chatBase - chatSeq++);
    const organizer = nextTg++;
    const res = await internal('POST', '/internal/mini-tournaments', {
      chatId: chatId.toString(),
      prize,
      organizer: { telegramId: organizer, name: 'Админ' },
      players: players.map((p) => ({ telegramId: p.tg, name: p.name })),
    });
    expect(res.statusCode).toBe(200);
    return { chatId, organizer };
  }

  /** Все садятся за стол, партия начинается сама; `loser` сдаётся. */
  async function playTable(chatId: bigint, seated: Player[], loser: Player): Promise<void> {
    const before = sent.length;
    const { roomId } = lastTable(chatId);
    for (const p of seated) expect((await join(p, roomId)).statusCode).toBe(200);
    const started = await loser.ws.waitFor((m) => m.type === 'GAME_STARTED' && m.roomId === roomId);
    if (started.type !== 'GAME_STARTED') throw new Error('unreachable');
    await loser.ws.send({ type: 'LEAVE_GAME', gameId: started.gameId });
    await until(() => sent.slice(before).some((m) => m.chatId === chatId && m.message.text.includes('Дураком остался')));
  }

  const offline = async (p: Player) => {
    p.ws.close();
    await until(() => !handle.ctx.realtime.hub.isOnline(p.id));
  };

  /** Все уже в Арене: стол открывается сам, никто не жмёт ни ссылку, ни «Готов»; `loser` сдаётся. */
  async function playOpenTable(chatId: bigint, loser: Player): Promise<void> {
    const before = sent.length;
    const { roomId } = lastTable(chatId);
    const started = await loser.ws.waitFor((m) => m.type === 'GAME_STARTED' && m.roomId === roomId);
    if (started.type !== 'GAME_STARTED') throw new Error('unreachable');
    await loser.ws.send({ type: 'LEAVE_GAME', gameId: started.gameId });
    await until(() => sent.slice(before).some((m) => m.chatId === chatId && m.message.text.includes('Дураком остался')));
  }

  it('six players, one does not come, then the fool of every table is out until one is left', async () => {
    const people = await Promise.all(['Аня', 'Боря', 'Вика', 'Гоша', 'Даня', 'Ева'].map(player));
    // Евы нет в Арене — за стол она не сядет
    await offline(people[5]!);
    const { chatId, organizer } = await start(people);

    // Первый стол — на всех шестерых, ссылка в группу, все упомянуты
    await until(() => lastTable(chatId).roomId !== '');
    const first = said(chatId).at(-1)!;
    expect(first).toContain('стол 1 на 6');
    for (const p of people) expect(first).toContain(`tg://user?id=${p.tg}`);
    expect(lastTable(chatId).link).toContain('https://t.me/BotMaruska_bot/play?startapp=game_');

    // Второй мини-турнир в той же группе не начать
    expect((await internal('POST', '/internal/mini-tournaments', {
      chatId: chatId.toString(), prize: 1, organizer: { telegramId: organizer, name: 'Админ' },
      players: people.slice(0, 2).map((p) => ({ telegramId: p.tg, name: p.name })),
    })).statusCode).toBe(409);

    // Ева не пришла: через секунду — техническое поражение и стол на пятерых
    const firstRoom = lastTable(chatId).roomId;
    const [anya, borya, vika, gosha, danya, eva] = people as [Player, Player, Player, Player, Player, Player];
    for (const p of [anya, borya, vika, gosha, danya]) expect((await join(p, firstRoom)).statusCode).toBe(200);
    await until(() => said(chatId).some((t) => t.includes('техническое поражение') && t.includes(`id=${eva.tg}`) && t.includes('6 место')));
    await until(() => lastTable(chatId).roomId !== firstRoom && said(chatId).at(-1)!.includes('стол 2 на 5'));

    // Дальше каждый стол на одного меньше: дураком остаётся тот, кто сдался
    await playTable(chatId, [anya, borya, vika, gosha, danya], danya);
    expect(said(chatId).find((t) => t.includes('Дураком остался') && t.includes(`id=${danya.tg}`))).toContain('5 место');
    await until(() => said(chatId).at(-1)!.includes('стол 3 на 4'));
    await playTable(chatId, [anya, borya, vika, gosha], gosha);
    await until(() => said(chatId).at(-1)!.includes('стол 4 на 3'));
    await playTable(chatId, [anya, borya, vika], vika);
    await until(() => said(chatId).at(-1)!.includes('стол 5 на 2'));
    await playTable(chatId, [anya, borya], borya);

    // Финал: победитель, таблица мест, приз в «Дурак Онлайн»; организатору — в личку
    await until(() => said(chatId).some((t) => t.includes('окончен!')));
    const final = said(chatId).find((t) => t.includes('окончен!'))!;
    expect(final).toContain(`Победитель — <a href="tg://user?id=${anya.tg}">`);
    expect(final).toContain('5 000 кредитов в «Дурак Онлайн»');
    expect(final.indexOf(`id=${anya.tg}`)).toBeLessThan(final.indexOf(`id=${borya.tg}`));
    const dm = sent.find((m) => m.chatId === BigInt(organizer))!;
    expect(dm.message.text).toContain('Выдай <b>5 000 кредитов в «Дурак Онлайн»</b>');
    expect(dm.message.text).toContain(`id=${anya.tg}`);

    const mini = await db.miniTournament.findFirstOrThrow({ where: { chatId }, include: { players: true } });
    expect(mini.status).toBe('FINISHED');
    const places = Object.fromEntries(mini.players.map((p) => [p.name, [p.place, p.outReason]]));
    expect(places).toEqual({
      Аня: [1, null], Боря: [2, 'game'], Вика: [3, 'game'], Гоша: [4, 'game'], Даня: [5, 'game'], Ева: [6, 'no_show'],
    });
    // Столы — переводной, подкидывают все, быстрые, без ничьей
    const rooms = await db.room.findMany({ where: { id: { in: [firstRoom] } } });
    expect(rooms[0]).toMatchObject({ variant: 'perevodnoy', throwIn: 'all', speed: 'fast', ending: 'nodraw', maxPlayers: 6 });
  }, 90_000);

  it('players already in the Arena sit down and start on their own: no link, no «Готов»', async () => {
    const people = await Promise.all(['Жора', 'Зоя', 'Игорь'].map(player));
    const [zhora, zoya, igor] = people as [Player, Player, Player];
    // Игорь вышел из Арены: стол ждёт его, а вернулся — сразу готов и партия начинается
    await offline(igor);
    const { chatId } = await start(people);
    await until(() => lastTable(chatId).roomId !== '');
    const { roomId } = lastTable(chatId);
    const room = handle.ctx.realtime.rooms.get(roomId)!;
    expect(room.seats.filter((s) => s.ready).map((s) => s.userId).sort()).toEqual([zhora.id, zoya.id].sort());
    expect(room.status).toBe('waiting');

    await igor.ws.connect();
    const started = await zhora.ws.waitFor((m) => m.type === 'GAME_STARTED' && m.roomId === roomId);
    if (started.type !== 'GAME_STARTED') throw new Error('unreachable');
    // Первый ход турнирной партии — 30 секунд, а не 15
    await zhora.ws.waitFor((m) => m.type === 'GAME_STATE');
    const first = zhora.ws.latest('GAME_STATE')!.state;
    expect(first.turnDeadline! - Date.now()).toBeGreaterThan(25_000);
    // Турнир — честная игра: подсветку карт не купить, и в состоянии её нет
    expect(await zhora.ws.send({ type: 'USE_FEATURE', gameId: started.gameId, feature: 'hints' })).toMatchObject({ type: 'ERROR', code: 'FORBIDDEN' });
    await zhora.ws.waitFor((m) => m.type === 'GAME_STATE');
    expect(zhora.ws.latest('GAME_STATE')!.features).toMatchObject({ hints: false, hintsAllowed: false });
    await igor.ws.send({ type: 'LEAVE_GAME', gameId: started.gameId });
    await until(() => said(chatId).at(-1)!.includes('стол 2 на 2'));

    // Следующий стол: оба в Арене — открывается и начинается сам
    await playOpenTable(chatId, zoya);
    await until(() => said(chatId).some((t) => t.includes('окончен!') && t.includes(`id=${zhora.tg}`)));
  }, 60_000);

  it('the organizer can call it off; nobody at the table ends it without a winner', async () => {
    const people = await Promise.all(['Жора', 'Зина', 'Игорь'].map(player));
    const { chatId } = await start(people, 0);
    await until(() => lastTable(chatId).roomId !== '');
    expect((await internal('GET', `/internal/mini-tournaments/active?chatId=${chatId}`)).json().tournament.players).toHaveLength(3);
    expect((await internal('POST', '/internal/mini-tournaments/cancel', { chatId: chatId.toString() })).json()).toEqual({ cancelled: true });
    expect(said(chatId).at(-1)).toContain('отменён организатором');
    expect((await internal('GET', `/internal/mini-tournaments/active?chatId=${chatId}`)).json().tournament).toBeNull();

    // Новый турнир: за стол не пришёл никто (оба не в Арене)
    const absent = await Promise.all(['Кира', 'Лёва'].map(player));
    for (const p of absent) await offline(p);
    const again = await start(absent, 0);
    await until(() => said(again.chatId).some((t) => t.includes('никто не пришёл')));
    expect((await db.miniTournament.findFirstOrThrow({ where: { chatId: again.chatId } })).status).toBe('CANCELLED');
  }, 30_000);

  it('rules come from the bot; the admin panel lists and cancels', async () => {
    const people = await Promise.all(['Нина', 'Олег'].map(player));
    // Не в Арене — стол ждёт их 90 секунд, как задал бот
    for (const p of people) await offline(p);
    const chatId = BigInt(chatBase - chatSeq++);
    const res = await internal('POST', '/internal/mini-tournaments', {
      chatId: chatId.toString(), prize: 300, organizer: { telegramId: nextTg++, name: 'Админ' },
      players: people.map((p) => ({ telegramId: p.tg, name: p.name })),
      rules: { variant: 'podkidnoy', throwIn: 'neighbors', speed: 'normal', readySeconds: 90 },
    });
    expect(res.statusCode).toBe(200);
    await until(() => lastTable(chatId).roomId !== '');
    expect(said(chatId).at(-1)).toContain('Заходите за стол — 90 с');
    const room = await db.room.findUniqueOrThrow({ where: { id: lastTable(chatId).roomId } });
    expect(room).toMatchObject({ variant: 'podkidnoy', throwIn: 'neighbors', speed: 'normal', ending: 'nodraw', maxPlayers: 2 });
    expect(handle.ctx.realtime.rooms.get(room.id)?.readyDeadline).toBeGreaterThan(Date.now() + 80_000);

    const list = (await internal('GET', '/internal/admin/mini-tournaments')).json();
    const mine = list.find((m: { chatId: string }) => m.chatId === chatId.toString());
    expect(mine).toMatchObject({ status: 'RUNNING', prize: 300, rules: { variant: 'podkidnoy', readySeconds: 90 } });
    expect(mine.players.map((p: { name: string }) => p.name)).toEqual(['Нина', 'Олег']);
    expect((await internal('POST', `/internal/admin/mini-tournaments/${mine.id}/cancel`)).statusCode).toBe(200);
    expect(said(chatId).at(-1)).toContain('отменён организатором');
    expect((await internal('POST', `/internal/admin/mini-tournaments/${mine.id}/cancel`)).statusCode).toBe(404);
  });

  it('somebody who never opened the Arena gets an account and can sit down', async () => {
    const known = await player('Миша');
    const stranger = { tg: nextTg++, name: 'Новичок' };
    const chatId = BigInt(chatBase - chatSeq++);
    const res = await internal('POST', '/internal/mini-tournaments', {
      chatId: chatId.toString(), prize: 0, organizer: { telegramId: nextTg++, name: 'Админ' },
      players: [{ telegramId: known.tg, name: known.name }, { telegramId: stranger.tg, name: stranger.name, username: 'newbie' }],
    });
    expect(res.statusCode).toBe(200);
    const user = await db.user.findUnique({ where: { telegramId: BigInt(stranger.tg) } });
    expect(user).toMatchObject({ firstName: 'Новичок', username: 'newbie' });
    await internal('POST', '/internal/mini-tournaments/cancel', { chatId: chatId.toString() });
  });
});
