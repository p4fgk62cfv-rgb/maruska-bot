import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { buildApp, type AppHandle } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { createContext } from '../src/context.js';
import { createDb, type Db } from '../src/db.js';
import { seedCatalog } from '../src/services/catalog.js';
import { plainGroupName } from '../src/services/miniTournaments.js';
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
    // Первый ход турнирной партии — 30 секунд, остальные — по 20
    await zhora.ws.waitFor((m) => m.type === 'GAME_STATE');
    const first = zhora.ws.latest('GAME_STATE')!.state;
    expect(first.turnDeadline! - Date.now()).toBeGreaterThan(25_000);
    expect(first.rules.turnMs).toBe(20_000);
    // Турнир — честная игра: подсветку карт не купить, и в состоянии её нет
    expect(await zhora.ws.send({ type: 'USE_FEATURE', gameId: started.gameId, feature: 'hints' })).toMatchObject({ type: 'ERROR', code: 'FORBIDDEN' });
    await zhora.ws.waitFor((m) => m.type === 'GAME_STATE');
    expect(zhora.ws.latest('GAME_STATE')!.features).toMatchObject({ hints: false, hintsAllowed: false, discardReminder: false });
    // …и отбой за монеты тоже нельзя
    expect(await zhora.ws.send({ type: 'USE_FEATURE', gameId: started.gameId, feature: 'discardReminder' })).toMatchObject({ type: 'ERROR', code: 'FORBIDDEN' });
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

  it('two tables: odd sign-ups at table А, even at table Б, the winners play the final 1 on 1', async () => {
    const people = await Promise.all(['Ада', 'Бэн', 'Вал', 'Гая', 'Дин', 'Ерик'].map(player));
    const [ada, ben, val, gaya, din, erik] = people as [Player, Player, Player, Player, Player, Player];
    const chatId = BigInt(chatBase - chatSeq++);
    const organizer = nextTg++;
    const res = await internal('POST', '/internal/mini-tournaments', {
      chatId: chatId.toString(), prize: 7000, tables: 2, organizer: { telegramId: organizer, name: 'Админ' },
      players: people.map((p) => ({ telegramId: p.tg, name: p.name })),
    });
    expect(res.statusCode).toBe(200);
    // Меньше двух человек на стол — нельзя
    expect((await internal('POST', '/internal/mini-tournaments', {
      chatId: String(chatId - 1n), prize: 1, tables: 2, organizer: { telegramId: organizer, name: 'Админ' },
      players: people.slice(0, 3).map((p) => ({ telegramId: p.tg, name: p.name })),
    })).statusCode).toBe(400);

    /** Ссылка последнего стола, в сообщении о котором есть `marker`. */
    const table = (marker: string) => {
      const msg = [...sent].reverse().find((m) => m.chatId === chatId && m.message.button && m.message.text.includes(marker));
      const link = msg && 'url' in msg.message.button! ? msg.message.button.url : '';
      return /game_([A-Z0-9]{8})/.exec(link)?.[1] ?? '';
    };
    /** Все в Арене — стол начинается сам; `loser` сдаётся. */
    const lose = async (marker: string, loser: Player, previous = '') => {
      await until(() => table(marker) !== '' && table(marker) !== previous);
      const roomId = table(marker);
      const started = await loser.ws.waitFor((m) => m.type === 'GAME_STARTED' && m.roomId === roomId, 10_000);
      if (started.type !== 'GAME_STARTED') throw new Error('unreachable');
      expect((await loser.ws.send({ type: 'LEAVE_GAME', gameId: started.gameId })).type).toBe('ACK');
      await until(() => said(chatId).some((t) => t.includes(`Дураком остался <a href="tg://user?id=${loser.tg}"`)));
      return roomId;
    };

    await until(() => table('стол А, партия 1') !== '' && table('стол Б, партия 1') !== '');
    const a1 = said(chatId).find((t) => t.includes('стол А, партия 1'))!;
    expect(a1).toContain('на 3 игрока');
    expect(a1).toContain('Победитель стола выходит в финал');
    for (const p of [ada, val, din]) expect(a1).toContain(`id=${p.tg}`);
    for (const p of [ben, gaya, erik]) expect(a1).not.toContain(`id=${p.tg}`);
    const roomA = handle.ctx.realtime.rooms.get(table('стол А'))!;
    expect(roomA.tournament?.title).toBe('Мини-турнир · стол А');

    // Кто ещё в турнире — в другой группе Мара его не запишет
    const playing = async (p: Player) => (await internal('GET', `/internal/mini-tournaments/playing?telegramId=${p.tg}`)).json().tournament;
    expect(await playing(din)).toEqual({ chatId: chatId.toString() });

    // Оба стола играют одновременно
    const ra = await lose('стол А, партия 1', din);
    expect(await playing(din)).toBeNull();
    expect(said(chatId).find((t) => t.includes(`Дураком остался <a href="tg://user?id=${din.tg}`))).toContain('5 место');
    const rb = await lose('стол Б, партия 1', erik);
    await lose('стол А, партия 2', val, ra);
    expect(said(chatId).find((t) => t.includes(`Дураком остался <a href="tg://user?id=${val.tg}`))).toContain('3 место');
    await until(() => said(chatId).some((t) => t.includes('Стол А окончен') && t.includes(`id=${ada.tg}`) && t.includes('выходит в финал')));
    // Пока стол Б не доигран, финала нет; победитель стола А ждёт его — он ещё в турнире
    expect(said(chatId).some((t) => t.includes('финал 1 на 1'))).toBe(false);
    expect(await playing(ada)).toEqual({ chatId: chatId.toString() });
    expect(await playing(val)).toBeNull();
    await lose('стол Б, партия 2', gaya, rb);

    // Финал: Ада против Бэна
    await until(() => table('финал 1 на 1') !== '');
    const final = said(chatId).find((t) => t.includes('финал 1 на 1'))!;
    expect(final).toContain(`id=${ada.tg}`);
    expect(final).toContain(`id=${ben.tg}`);
    await lose('финал 1 на 1', ben);
    expect(said(chatId).find((t) => t.includes('Финал окончен'))).toContain('2 место');

    await until(() => said(chatId).some((t) => t.includes('окончен!')));
    const end = said(chatId).find((t) => t.includes('окончен!'))!;
    expect(end).toContain(`Победитель — <a href="tg://user?id=${ada.tg}">`);
    expect(end).toContain('7 000 кредитов');
    expect(sent.find((m) => m.chatId === BigInt(organizer))!.message.text).toContain(`id=${ada.tg}`);

    const mini = await db.miniTournament.findFirstOrThrow({ where: { chatId, parentId: null }, include: { players: true } });
    expect(mini.status).toBe('FINISHED');
    expect(mini.winnerId).toBe(ada.id);
    expect(Object.fromEntries(mini.players.map((p) => [p.name, p.place]))).toEqual({ Ада: 1, Бэн: 2, Вал: 3, Гая: 3, Дин: 5, Ерик: 5 });
    expect((await internal('GET', `/internal/mini-tournaments/active?chatId=${chatId}`)).json().tournament).toBeNull();
    expect(await playing(ada)).toBeNull();
    const listed = (await internal('GET', '/internal/admin/mini-tournaments')).json().filter((m: { chatId: string }) => m.chatId === chatId.toString());
    expect(listed).toHaveLength(1);
    expect(listed[0]).toMatchObject({ tables: 2, status: 'FINISHED' });
  }, 90_000);

  it('a group title in ornaments becomes plain letters: «꧁ᬊ 𝑫𝑰𝑨𝑴💎𝑵𝑫ᬊ꧂» → «DIAMOND»', () => {
    expect(plainGroupName('꧁ᬊ 𝑫𝑰𝑨𝑴💎𝑵𝑫ᬊ꧂')).toBe('DIAMOND');
    expect(plainGroupName('Вегас 🎰')).toBe('Вегас');
    expect(plainGroupName('DIAM◯ND')).toBe('DIAMOND');
    expect(plainGroupName('🔥🔥')).toBe('');
  });

  it('two groups: each group plays its own table, the final and the result go to both groups', async () => {
    const people = await Promise.all(['Вега1', 'Вега2', 'Диа1', 'Диа2'].map(player));
    const [v1, v2, d1, d2] = people as [Player, Player, Player, Player];
    const vegas = BigInt(chatBase - chatSeq++);
    const diamant = BigInt(chatBase - chatSeq++);
    const organizer = nextTg++;
    const res = await internal('POST', '/internal/mini-tournaments', {
      chatId: vegas.toString(), prize: 3000, tables: 2, organizer: { telegramId: organizer, name: 'Админ' },
      groups: [{ chatId: vegas.toString(), name: 'Вегас' }, { chatId: diamant.toString(), name: 'Диамант' }],
      players: [...[v1, v2].map((p) => ({ telegramId: p.tg, name: p.name, table: 0 })), ...[d1, d2].map((p) => ({ telegramId: p.tg, name: p.name, table: 1 }))],
    });
    expect(res.statusCode).toBe(200);
    // Ни в одной из двух групп второй турнир не начать
    expect((await internal('GET', `/internal/mini-tournaments/active?chatId=${diamant}`)).json().tournament.players).toHaveLength(4);
    expect((await internal('POST', '/internal/mini-tournaments', {
      chatId: diamant.toString(), prize: 1, organizer: { telegramId: organizer, name: 'Админ' },
      players: [d1, d2].map((p) => ({ telegramId: nextTg++, name: p.name })),
    })).statusCode).toBe(409);

    /** Ссылка последнего стола в группе `chat`, в сообщении о котором есть `marker`. */
    const table = (chat: bigint, marker: string) => {
      const msg = [...sent].reverse().find((m) => m.chatId === chat && m.message.button && m.message.text.includes(marker));
      const link = msg && 'url' in msg.message.button! ? msg.message.button.url : '';
      return /game_([A-Z0-9]{8})/.exec(link)?.[1] ?? '';
    };
    const lose = async (chat: bigint, marker: string, loser: Player) => {
      await until(() => table(chat, marker) !== '');
      const roomId = table(chat, marker);
      const started = await loser.ws.waitFor((m) => m.type === 'GAME_STARTED' && m.roomId === roomId, 10_000);
      if (started.type !== 'GAME_STARTED') throw new Error('unreachable');
      expect((await loser.ws.send({ type: 'LEAVE_GAME', gameId: started.gameId })).type).toBe('ACK');
      await until(() => said(chat).some((t) => t.includes(`Дураком остался <a href="tg://user?id=${loser.tg}"`)));
    };

    // Стол «Вегаса» — только в «Вегасе», стол «Диаманта» — только в «Диаманте»
    await until(() => table(vegas, 'стол «Вегас», партия 1') !== '' && table(diamant, 'стол «Диамант», партия 1') !== '');
    expect(said(vegas).some((t) => t.includes('«Диамант»'))).toBe(false);
    expect(said(diamant).find((t) => t.includes('партия 1'))).toContain(`id=${d1.tg}`);
    expect(handle.ctx.realtime.rooms.get(table(vegas, 'стол «Вегас»'))!.tournament?.title).toBe('Мини-турнир · стол «Вегас»');

    await lose(vegas, 'стол «Вегас», партия 1', v2);
    // Победа стола — новость для обеих групп
    for (const chat of [vegas, diamant]) await until(() => said(chat).some((t) => t.includes('Стол «Вегас» окончен') && t.includes(`id=${v1.tg}`)));
    await lose(diamant, 'стол «Диамант», партия 1', d2);

    // Финал — ссылка в обе группы
    for (const chat of [vegas, diamant]) await until(() => table(chat, 'финал 1 на 1') !== '');
    expect(table(vegas, 'финал 1 на 1')).toBe(table(diamant, 'финал 1 на 1'));
    await lose(vegas, 'финал 1 на 1', d1);
    for (const chat of [vegas, diamant]) {
      await until(() => said(chat).some((t) => t.includes('окончен!')));
      expect(said(chat).find((t) => t.includes('окончен!'))).toContain(`Победитель — <a href="tg://user?id=${v1.tg}">`);
    }
    const mini = await db.miniTournament.findFirstOrThrow({ where: { chatId: vegas, parentId: null }, include: { players: true } });
    expect(Object.fromEntries(mini.players.map((p) => [p.name, p.place]))).toEqual({ Вега1: 1, Диа1: 2, Вега2: 3, Диа2: 3 });
    expect((await internal('GET', `/internal/mini-tournaments/active?chatId=${diamant}`)).json().tournament).toBeNull();
  }, 90_000);

  it('two groups: either group can call it off', async () => {
    const people = await Promise.all(['Ки1', 'Ки2', 'Ло1', 'Ло2'].map(player));
    for (const p of people) await offline(p);
    const a = BigInt(chatBase - chatSeq++);
    const b = BigInt(chatBase - chatSeq++);
    expect((await internal('POST', '/internal/mini-tournaments', {
      chatId: a.toString(), prize: 0, tables: 2, organizer: { telegramId: nextTg++, name: 'Админ' },
      groups: [{ chatId: a.toString(), name: 'А-группа' }, { chatId: b.toString(), name: 'Б-группа' }],
      players: people.map((p, i) => ({ telegramId: p.tg, name: p.name, table: i < 2 ? 0 : 1 })),
    })).statusCode).toBe(200);
    expect((await internal('POST', '/internal/mini-tournaments/cancel', { chatId: b.toString() })).json()).toEqual({ cancelled: true });
    for (const chat of [a, b]) expect(said(chat).at(-1)).toContain('отменён организатором');
    expect((await db.miniTournament.findMany({ where: { chatId: { in: [a, b] } } })).every((r) => r.status === 'CANCELLED')).toBe(true);
  }, 30_000);

  it('two tables: the organizer calls it off — both tables close', async () => {
    const people = await Promise.all(['Ия', 'Ян', 'Юля', 'Эд'].map(player));
    for (const p of people) await offline(p);
    const chatId = BigInt(chatBase - chatSeq++);
    expect((await internal('POST', '/internal/mini-tournaments', {
      chatId: chatId.toString(), prize: 0, tables: 2, organizer: { telegramId: nextTg++, name: 'Админ' },
      players: people.map((p) => ({ telegramId: p.tg, name: p.name })),
    })).statusCode).toBe(200);
    await until(() => said(chatId).filter((t) => t.includes('партия 1 на 2')).length === 2);
    expect((await internal('GET', `/internal/mini-tournaments/active?chatId=${chatId}`)).json().tournament.players).toHaveLength(4);
    expect((await internal('POST', '/internal/mini-tournaments/cancel', { chatId: chatId.toString() })).json()).toEqual({ cancelled: true });
    const rows = await db.miniTournament.findMany({ where: { chatId } });
    expect(rows).toHaveLength(3);
    expect(rows.every((r) => r.status === 'CANCELLED')).toBe(true);
  }, 30_000);

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
