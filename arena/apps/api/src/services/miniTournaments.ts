import { roomDeepLink, type GameResultDto } from '@arena/shared';
import type { FastifyBaseLogger } from 'fastify';
import { z } from 'zod';
import type { Config } from '../config.js';
import type { Db } from '../db.js';
import type { MiniTournament, MiniTournamentPlayer } from '../generated/prisma/client.js';
import { AppError } from '../lib/errors.js';
import { inviteCode } from '../lib/ids.js';
import { SerialQueue } from '../lib/serial.js';
import type { Realtime } from '../realtime/realtime.js';
import type { Room } from '../realtime/types.js';
import type { TelegramBot } from './notifier.js';
import type { UserService } from './users.js';
import { journal } from '../lib/journal.js';

/** Стол мини-турнира: переводной, подкидывают все, быстро, без ничьей. */
export const MINI_SETTINGS = {
  variant: 'perevodnoy',
  throwIn: 'all',
  fairness: 'fair',
  ending: 'nodraw',
  speed: 'fast',
  deckSize: 36,
} as const;

export const MINI_MIN_PLAYERS = 2;
/** За одним столом. */
export const MINI_MAX_PLAYERS = 6;
export const MINI_MAX_TABLES = 2;
/** Столы первого этапа турнира на два стола; их победители играют финал. */
const LABELS = ['А', 'Б'] as const;
const FINAL = 'финал';

const person = z.object({ telegramId: z.coerce.bigint(), name: z.string().min(1).max(128), username: z.string().max(64).nullish() });

/** Правила стола и сколько ждать у стола — их задают в админке Мары. */
export const miniRulesSchema = z.object({
  variant: z.enum(['podkidnoy', 'perevodnoy']).default(MINI_SETTINGS.variant),
  throwIn: z.enum(['all', 'neighbors']).default(MINI_SETTINGS.throwIn),
  speed: z.enum(['normal', 'fast']).default(MINI_SETTINGS.speed),
  readySeconds: z.number().int().min(15).max(600).optional(),
});
export type MiniRules = z.infer<typeof miniRulesSchema>;

export const startMiniSchema = z
  .object({
    chatId: z.coerce.bigint(),
    title: z.string().min(3).max(128).default('Мини-турнир'),
    prize: z.number().int().min(0).max(1_000_000_000),
    organizer: person,
    players: z.array(person).min(MINI_MIN_PLAYERS).max(MINI_MAX_PLAYERS * MINI_MAX_TABLES),
    /** 2 — два стола: игроки по очереди записи садятся за стол А и стол Б. */
    tables: z.number().int().min(1).max(MINI_MAX_TABLES).default(1),
    rules: miniRulesSchema.default({ variant: MINI_SETTINGS.variant, throwIn: MINI_SETTINGS.throwIn, speed: MINI_SETTINGS.speed }),
  })
  .refine((v) => v.players.length >= MINI_MIN_PLAYERS * v.tables && v.players.length <= MINI_MAX_PLAYERS * v.tables, {
    message: 'players do not fit the tables',
    path: ['players'],
  });
export type StartMini = z.infer<typeof startMiniSchema>;

type Player = MiniTournamentPlayer;
type Mini = MiniTournament & { players: Player[] };

export function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

export function mention(p: Pick<Player, 'telegramId' | 'name'>): string {
  return `<a href="tg://user?id=${p.telegramId}">${escapeHtml(p.name)}</a>`;
}

const formatCredits = (n: bigint) => n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ');

/**
 * Мини-турнир группы: один стол на вылет.
 *
 * Все записавшиеся садятся за один стол. Кто остался дураком — выбывает, и стол
 * пересоздаётся на одного меньше: 6 → 5 → 4 → 3 → 2. Не зашёл за стол за минуту
 * или ушёл из-за стола — техническое поражение, стол тут же пересоздаётся без него.
 * Последний оставшийся — победитель. Обо всём Арена сама пишет в группу (тем же
 * ботом, что и Мара), а организатору — в личку, кому выдать приз в «Дурак Онлайн».
 *
 * Турнир на два стола: игроки по очереди записи садятся за стол А и стол Б, оба
 * стола играют на вылет одновременно. Каждый стол — свой турнир (parentId — общий
 * турнир, у которого своего стола нет). Победители столов играют финал 1 на 1 —
 * третий такой же стол. Места: финалисты — 1 и 2, дальше места делят столы:
 * вторые за столами — оба 3-и, третьи — оба 5-е и так далее.
 *
 * Всё меняется через одну очередь; `tick()` раз в несколько секунд поднимает стол,
 * если его нет (после перезапуска сервера или когда игрок ещё доигрывает другую партию).
 */
export class MiniTournamentService {
  private readonly queue = new SerialQueue();
  private timer: NodeJS.Timeout | null = null;

  constructor(
    private readonly deps: {
      config: Config;
      db: Db;
      users: UserService;
      realtime: Realtime;
      bot: Pick<TelegramBot, 'send'>;
      log: FastifyBaseLogger;
    },
  ) {}

  private get db(): Db {
    return this.deps.db;
  }

  start(intervalMs = 5000): void {
    this.timer = setInterval(() => void this.tick().catch((e) => this.fail(e)), intervalMs);
    this.timer.unref();
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
  }

  private fail(error: unknown): void {
    this.deps.log.error({ err: error }, 'mini-tournament job failed');
  }

  // ── запуск ─────────────────────────────────────────────────

  /** Мара набрала стол: создаём турнир и сажаем всех за первый стол. */
  async create(input: StartMini): Promise<{ id: string }> {
    const ids = new Set(input.players.map((p) => p.telegramId));
    if (ids.size !== input.players.length) throw new AppError('VALIDATION_FAILED');
    const busy = await this.db.miniTournament.count({ where: { chatId: input.chatId, status: 'RUNNING', parentId: null } });
    // В группе уже идёт мини-турнир: второй не начинаем.
    if (busy) throw new AppError('DUPLICATE_REQUEST');

    const users: string[] = [];
    for (const p of input.players) users.push(await this.account(p));

    const base = {
      chatId: input.chatId,
      title: input.title,
      organizerTelegramId: input.organizer.telegramId,
      organizerName: input.organizer.name.slice(0, 128),
      settings: input.rules,
      tables: input.tables,
    };
    const seat = (p: StartMini['players'][number], i: number) => ({ userId: users[i]!, telegramId: p.telegramId, name: p.name.slice(0, 128), seat: i });
    const mini = await this.db.miniTournament.create({
      data: { ...base, prize: BigInt(input.prize), players: { create: input.players.map(seat) } },
    });
    if (input.tables === 1) {
      await this.queue.run(() => this.openTable(mini.id));
      return { id: mini.id };
    }
    // Два стола: 1-й, 3-й, 5-й… записавшийся — за стол А, 2-й, 4-й, 6-й… — за стол Б.
    const tables: string[] = [];
    for (let t = 0; t < input.tables; t++) {
      const table = await this.db.miniTournament.create({
        data: {
          ...base,
          parentId: mini.id,
          label: LABELS[t]!,
          players: { create: input.players.map(seat).filter((p) => p.seat % input.tables === t) },
        },
      });
      tables.push(table.id);
    }
    await this.queue.run(async () => {
      for (const id of tables) await this.openTable(id);
    });
    return { id: mini.id };
  }

  /** Аккаунт Арены для человека из группы: есть — берём, нет — заводим (как при первом входе). */
  private async account(p: z.infer<typeof person>): Promise<string> {
    const found = await this.db.user.findUnique({ where: { telegramId: p.telegramId }, select: { id: true } });
    if (found) return found.id;
    const user = await this.deps.users.upsertFromTelegram({ id: Number(p.telegramId), first_name: p.name, username: p.username ?? undefined });
    return user.id;
  }

  /** Админ группы отменил турнир, пока он идёт. */
  async cancel(chatId: bigint): Promise<boolean> {
    return this.queue.run(async () => {
      const mini = await this.db.miniTournament.findFirst({ where: { chatId, status: 'RUNNING', parentId: null } });
      if (!mini) return false;
      await this.db.miniTournament.update({ where: { id: mini.id }, data: { status: 'CANCELLED', finishedAt: new Date() } });
      await this.closeRoom(mini.roomId);
      const tables = await this.db.miniTournament.findMany({ where: { parentId: mini.id, status: 'RUNNING' } });
      for (const t of tables) {
        await this.db.miniTournament.update({ where: { id: t.id }, data: { status: 'CANCELLED', finishedAt: new Date() } });
        await this.closeRoom(t.roomId);
      }
      await this.say(mini, `🛑 <b>${escapeHtml(mini.title)}</b> отменён организатором.`);
      return true;
    });
  }

  async active(chatId: bigint): Promise<{ id: string; round: number; players: { name: string; out: boolean }[] } | null> {
    const mini = await this.db.miniTournament.findFirst({ where: { chatId, status: 'RUNNING', parentId: null }, include: { players: { orderBy: { seat: 'asc' } } } });
    if (!mini) return null;
    return { id: mini.id, round: mini.round, players: mini.players.map((p) => ({ name: p.name, out: p.outRound !== null || p.place !== null })) };
  }

  private async tick(): Promise<void> {
    await this.queue.run(async () => {
      const running = await this.db.miniTournament.findMany({ where: { status: 'RUNNING' } });
      const rooms = this.deps.realtime.rooms;
      for (const mini of running) {
        // Турнир на два стола сам не играет: только проверяет, не пора ли финал (после перезапуска сервера).
        if (this.isParent(mini)) {
          await this.stageDone(mini.id);
          continue;
        }
        if (mini.roomId && rooms.get(mini.roomId)) continue;
        await this.openTable(mini.id, true);
      }
    });
  }

  // ── стол ───────────────────────────────────────────────────

  private alive(players: Player[]): Player[] {
    return players.filter((p) => p.outRound === null).sort((a, b) => a.seat - b.seat);
  }

  /** Сажает всех оставшихся за новый стол и даёт в группе ссылку. Один остался — он победил. */
  private async openTable(miniId: string, quiet = false): Promise<void> {
    const mini = await this.db.miniTournament.findUnique({ where: { id: miniId }, include: { players: true } });
    if (!mini || mini.status !== 'RUNNING') return;
    if (this.isParent(mini)) return;
    const left = this.alive(mini.players);
    if (left.length === 1) {
      await this.finish(mini, left[0]!);
      return;
    }
    if (left.length === 0) {
      await this.db.miniTournament.update({ where: { id: mini.id }, data: { status: 'CANCELLED', finishedAt: new Date() } });
      if (mini.parentId) {
        await this.say(mini, `🛑 ${mini.label === FINAL ? 'На финал' : `За стол ${mini.label}`} никто не пришёл.`);
        await this.stageDone(mini.parentId);
        return;
      }
      await this.say(mini, `🛑 <b>${escapeHtml(mini.title)}</b>: за стол никто не пришёл — турнир закрыт без победителя.`);
      return;
    }
    const round = mini.round + 1;
    const rules = this.rules(mini);
    let room: Room;
    try {
      room = await this.deps.realtime.rooms.createMatchRoom(
        { id: mini.id, title: this.name(mini), round, matchId: mini.id, kind: 'mini', readyMs: this.seconds(mini) * 1000 },
        left.map((p) => p.userId),
        { ...MINI_SETTINGS, variant: rules.variant, throwIn: rules.throwIn, speed: rules.speed },
      );
    } catch (error) {
      // Кто-то ещё доигрывает другую партию: стол поднимет следующий tick.
      if (error instanceof AppError && error.code === 'ALREADY_IN_ROOM') {
        if (!quiet) await this.say(mini, '⏳ Кто-то из участников ещё доигрывает другую партию — стол откроется, как только он освободится.');
        return;
      }
      throw error;
    }
    await this.db.miniTournament.update({ where: { id: mini.id }, data: { round, roomId: room.id } });
    const link = roomDeepLink(this.deps.config.BOT_USERNAME, this.deps.config.MINI_APP_SHORT_NAME || null, room.id, inviteCode(room.id, this.deps.config.SESSION_SECRET));
    const seconds = this.seconds(mini);
    const head =
      mini.label === FINAL
        ? `🏆 <b>${escapeHtml(mini.title)}</b> · финал 1 на 1\n\n${left.map(mention).join(' — ')}`
        : `🃏 <b>${escapeHtml(mini.title)}</b> · ${this.tableName(mini, round)} на ${left.length} ${left.length >= 5 ? 'игроков' : 'игрока'}\n\n` +
          left.map(mention).join(', ');
    const next = mini.parentId && mini.label !== FINAL && round === 1 ? 'Победитель стола выходит в финал. ' : '';
    await this.say(
      mini,
      `${head}\n\n${next}Заходите за стол — ${seconds} с. Партия начнётся сама, когда сядут все. Кто не придёт — техническое поражение.`,
      { text: '🎮 За стол', url: link },
    );
  }

  /** Турнир на два стола: у него самого стола нет, играют его столы. */
  private isParent(mini: Pick<MiniTournament, 'parentId' | 'tables'>): boolean {
    return mini.parentId === null && mini.tables > 1;
  }

  /** Как стол называется в Арене: «Мини-турнир · стол А». */
  private name(mini: Pick<MiniTournament, 'title' | 'label'>): string {
    if (!mini.label) return mini.title;
    return `${mini.title} · ${mini.label === FINAL ? 'финал' : `стол ${mini.label}`}`;
  }

  /** «стол 2» — один стол; «стол А, партия 2» — турнир на два стола. */
  private tableName(mini: Pick<MiniTournament, 'label'>, round: number): string {
    if (!mini.label) return `стол ${round}`;
    return mini.label === FINAL ? 'финал' : `стол ${mini.label}, партия ${round}`;
  }

  private ended(mini: Pick<MiniTournament, 'label' | 'round'>): string {
    if (!mini.label) return `Стол ${mini.round} окончен`;
    return mini.label === FINAL ? 'Финал окончен' : `Стол ${mini.label}: партия ${mini.round} окончена`;
  }

  /** Место в турнире по месту за столом: за столами первого этапа места делят — 3, 3, 5, 5… */
  private placeOf(mini: Pick<MiniTournament, 'parentId' | 'label' | 'tables'>, place: number): number {
    return mini.parentId && mini.label !== FINAL ? (place - 1) * mini.tables + 1 : place;
  }

  private rules(mini: Pick<MiniTournament, 'settings'>): MiniRules {
    const parsed = miniRulesSchema.safeParse(mini.settings ?? {});
    return parsed.success ? parsed.data : miniRulesSchema.parse({});
  }

  /** Сколько ждать у стола: из настроек турнира, иначе — переменная арены. */
  private seconds(mini: Pick<MiniTournament, 'settings'>): number {
    return this.rules(mini).readySeconds ?? this.deps.config.MINI_TOURNAMENT_READY_SECONDS;
  }

  /** Админка: последние мини-турниры всех групп. */
  async list(): Promise<object[]> {
    const rows = await this.db.miniTournament.findMany({ where: { parentId: null }, orderBy: { createdAt: 'desc' }, take: 30, include: { players: { orderBy: { seat: 'asc' } } } });
    return rows.map((m) => ({
      id: m.id,
      chatId: m.chatId.toString(),
      status: m.status,
      round: m.round,
      tables: m.tables,
      prize: Number(m.prize),
      organizer: m.organizerName,
      rules: this.rules(m),
      createdAt: m.createdAt.toISOString(),
      finishedAt: m.finishedAt?.toISOString() ?? null,
      players: m.players.map((p) => ({ name: p.name, telegramId: p.telegramId.toString(), place: p.place, out: p.outReason })),
    }));
  }

  /** Админка: отменить идущий мини-турнир по id. */
  async cancelById(id: string): Promise<boolean> {
    const mini = await this.db.miniTournament.findUnique({ where: { id } });
    return mini && mini.status === 'RUNNING' ? this.cancel(mini.chatId) : false;
  }

  private async closeRoom(roomId: string | null): Promise<void> {
    if (!roomId) return;
    const room = this.deps.realtime.rooms.get(roomId);
    if (room && room.status === 'waiting') await this.deps.realtime.rooms.closeMatchRoom(room).catch(() => undefined);
  }

  // ── исходы (их вызывает Арена) ─────────────────────────────

  onFinished(room: Room, result: GameResultDto | null): Promise<void> {
    return this.queue.run(async () => {
      const mini = await this.current(room);
      if (!mini) return;
      if (!result || result.kind !== 'loser' || !result.loserId) {
        // Партия сорвалась (сервер, отмена): тот же состав садится заново.
        journal.record({ kind: 'replay', miniId: mini.id, roomId: room.id, details: { round: mini.round, reason: result?.reason ?? null } });
        const where = !mini.label ? '' : mini.label === FINAL ? 'Финал: п' : `Стол ${mini.label}: п`;
        await this.say(mini, `♻️ ${where || 'П'}артия не доиграна — переигрываем тем же составом.`);
        await this.openTable(mini.id, true);
        return;
      }
      const loser = mini.players.find((p) => p.userId === result.loserId);
      if (!loser) return;
      const place = this.alive(mini.players).length;
      await this.out(mini, [loser], 'game', place);
      const left = this.alive(mini.players.map((p) => (p.userId === loser.userId ? { ...p, outRound: mini.round } : p)));
      await this.say(
        mini,
        `💥 ${this.ended(mini)}. Дураком остался ${mention(loser)} — <b>${this.placeOf(mini, place)} место</b>.\n` +
          (left.length > 1 ? `Остались: ${left.map(mention).join(', ')}` : ''),
      );
      await this.openTable(mini.id, true);
    });
  }

  onNoShow(room: Room, ready: string[]): Promise<void> {
    return this.queue.run(async () => {
      const mini = await this.current(room);
      if (!mini) return;
      const absent = this.alive(mini.players).filter((p) => !ready.includes(p.userId));
      if (!absent.length) return;
      const place = this.alive(mini.players).length;
      await this.out(mini, absent, 'no_show', place);
      for (const p of absent) journal.record({ kind: 'no_show', miniId: mini.id, roomId: room.id, userId: p.userId, details: { round: mini.round, name: p.name } });
      const seconds = this.seconds(mini);
      await this.say(
        mini,
        `⏰ Не пришли за стол за ${seconds} с — техническое поражение: ${absent
          .map((p, i) => `${mention(p)} (${this.placeOf(mini, place - i)} место)`)
          .join(', ')}.`,
      );
      await this.openTable(mini.id, true);
    });
  }

  onForfeit(room: Room, userId: string): Promise<void> {
    return this.queue.run(async () => {
      const mini = await this.current(room);
      if (!mini) return;
      const player = this.alive(mini.players).find((p) => p.userId === userId);
      if (!player) return;
      const place = this.alive(mini.players).length;
      await this.out(mini, [player], 'left', place);
      journal.record({ kind: 'forfeit', miniId: mini.id, roomId: room.id, userId: player.userId, details: { round: mini.round, name: player.name } });
      await this.say(mini, `🚪 ${mention(player)} ушёл из-за стола — техническое поражение, <b>${this.placeOf(mini, place)} место</b>.`);
      // Стол закрывается вместе с уходом: остальных сажаем за новый.
      await this.db.miniTournament.update({ where: { id: mini.id }, data: { roomId: null } });
      await this.openTable(mini.id, true);
    });
  }

  private async current(room: Room): Promise<Mini | null> {
    const id = room.tournament?.kind === 'mini' ? room.tournament.id : null;
    if (!id) return null;
    const mini = await this.db.miniTournament.findUnique({ where: { id }, include: { players: true } });
    // Устаревший стол (уже пересоздан или турнир закрыт) ничего не решает.
    if (!mini || mini.status !== 'RUNNING' || mini.roomId !== room.id) return null;
    return mini;
  }

  /** Выбывают: место — по числу оставшихся (несколько сразу — по порядку записи, с конца). */
  private async out(mini: Mini, players: Player[], reason: string, place: number): Promise<void> {
    await this.db.$transaction(
      players.map((p, i) =>
        this.db.miniTournamentPlayer.update({
          where: { miniId_userId: { miniId: mini.id, userId: p.userId } },
          data: { outRound: mini.round, outReason: reason, place: place - i },
        }),
      ),
    );
    for (const p of players) {
      const local = mini.players.find((x) => x.userId === p.userId);
      if (local) local.outRound = mini.round;
    }
  }

  private async finish(mini: Mini, winner: Player): Promise<void> {
    if (mini.parentId) {
      await this.tableWon(mini, winner);
      return;
    }
    const claimed = await this.db.miniTournament.updateMany({
      where: { id: mini.id, status: 'RUNNING' },
      data: { status: 'FINISHED', finishedAt: new Date(), winnerId: winner.userId, roomId: null },
    });
    if (!claimed.count) return;
    await this.db.miniTournamentPlayer.update({ where: { miniId_userId: { miniId: mini.id, userId: winner.userId } }, data: { place: 1 } });

    const places = mini.players
      .map((p) => ({ ...p, place: p.userId === winner.userId ? 1 : (p.place ?? mini.players.length) }))
      .sort((a, b) => a.place - b.place);
    const medal = (n: number) => (n === 1 ? '🥇' : n === 2 ? '🥈' : n === 3 ? '🥉' : `${n}.`);
    const prize = mini.prize > 0n ? `\n\n💰 Приз — <b>${formatCredits(mini.prize)} кредитов в «Дурак Онлайн»</b>. Его выдаст организатор.` : '';
    await this.say(
      mini,
      `🏆 <b>${escapeHtml(mini.title)}</b> окончен!\n\nПобедитель — ${mention(winner)}! Поздравляем! 🎉${prize}\n\n` +
        places.map((p) => `${medal(p.place)} ${mention(p)}`).join('\n'),
    );

    if (mini.prize > 0n) {
      const note =
        `🏆 <b>${escapeHtml(mini.title)}</b> окончен.\n\nВыдай <b>${formatCredits(mini.prize)} кредитов в «Дурак Онлайн»</b> ` +
        `победителю: ${mention(winner)} (Telegram ID ${winner.telegramId}).`;
      const outcome = await this.deps.bot.send(mini.organizerTelegramId, { text: note });
      if (outcome !== 'ok') {
        // Организатор не писал боту в личку — напоминаем в группе.
        await this.say(mini, `📌 ${mention({ telegramId: mini.organizerTelegramId, name: mini.organizerName })}, выдай приз победителю ${mention(winner)}.`);
      }
    }
  }

  // ── турнир на два стола ────────────────────────────────────

  /** За столом остался один: стол первого этапа выводит его в финал, финал — решает турнир. */
  private async tableWon(table: Mini, winner: Player): Promise<void> {
    const claimed = await this.db.miniTournament.updateMany({
      where: { id: table.id, status: 'RUNNING' },
      data: { status: 'FINISHED', finishedAt: new Date(), winnerId: winner.userId, roomId: null },
    });
    if (!claimed.count) return;
    await this.db.miniTournamentPlayer.update({ where: { miniId_userId: { miniId: table.id, userId: winner.userId } }, data: { place: 1 } });
    if (table.label !== FINAL) await this.say(table, `🏅 Стол ${table.label} окончен: побеждает ${mention(winner)} и выходит в финал!`);
    await this.stageDone(table.parentId!);
  }

  /**
   * Что дальше у турнира на два стола: переносит места со столов в общий турнир; оба стола
   * доиграны — сажает их победителей за финал; финал доигран — объявляет победителя.
   * Вызывать можно сколько угодно раз: ничего не повторит.
   */
  private async stageDone(parentId: string): Promise<void> {
    const parent = await this.db.miniTournament.findUnique({ where: { id: parentId } });
    if (!parent || parent.status !== 'RUNNING') return;
    const tables = await this.db.miniTournament.findMany({ where: { parentId }, include: { players: true }, orderBy: { createdAt: 'asc' } });
    for (const t of tables) {
      for (const p of t.players) {
        if (p.place === null || (p.place === 1 && t.label !== FINAL)) continue;
        await this.db.miniTournamentPlayer.update({
          where: { miniId_userId: { miniId: parentId, userId: p.userId } },
          data: { place: this.placeOf(t, p.place), outRound: p.outRound, outReason: p.outReason },
        });
      }
    }
    const reload = () => this.db.miniTournament.findUniqueOrThrow({ where: { id: parentId }, include: { players: true } });

    const final = tables.find((t) => t.label === FINAL);
    if (final) {
      if (final.status === 'RUNNING') return;
      const all = await reload();
      const champion = final.status === 'FINISHED' ? all.players.find((p) => p.userId === final.winnerId) : undefined;
      if (champion) await this.finish(all, champion);
      else await this.noWinner(parent, 'на финал никто не пришёл');
      return;
    }
    const stage = tables.filter((t) => t.label !== FINAL);
    if (stage.some((t) => t.status === 'RUNNING')) return;
    const all = await reload();
    const winners = stage
      .filter((t) => t.status === 'FINISHED' && t.winnerId)
      .map((t) => all.players.find((p) => p.userId === t.winnerId))
      .filter((p): p is Player => p !== undefined);
    if (winners.length === 1) {
      // Второй стол остался без победителя (никто не пришёл): турнир выигран без финала.
      await this.finish(all, winners[0]!);
      return;
    }
    if (winners.length === 0) {
      await this.noWinner(parent, 'за столы никто не пришёл');
      return;
    }
    const table = await this.db.miniTournament.create({
      data: {
        chatId: parent.chatId,
        title: parent.title,
        organizerTelegramId: parent.organizerTelegramId,
        organizerName: parent.organizerName,
        settings: parent.settings ?? {},
        tables: parent.tables,
        parentId,
        label: FINAL,
        players: { create: winners.map((p) => ({ userId: p.userId, telegramId: p.telegramId, name: p.name, seat: p.seat })) },
      },
    });
    await this.openTable(table.id);
  }

  private async noWinner(parent: MiniTournament, why: string): Promise<void> {
    await this.db.miniTournament.update({ where: { id: parent.id }, data: { status: 'CANCELLED', finishedAt: new Date() } });
    await this.say(parent, `🛑 <b>${escapeHtml(parent.title)}</b>: ${why} — турнир закрыт без победителя.`);
  }

  private async say(mini: Pick<MiniTournament, 'chatId'> & { id?: string }, text: string, button?: { text: string; url: string }): Promise<void> {
    const outcome = await this.deps.bot.send(mini.chatId, button ? { text, button } : { text });
    if (outcome !== 'ok') {
      this.deps.log.warn({ chatId: mini.chatId.toString(), outcome }, 'mini-tournament message not delivered');
      journal.record({
        kind: 'message_lost', miniId: mini.id ?? null,
        details: { chatId: mini.chatId.toString(), outcome, text: text.replace(/<[^>]+>/g, '').slice(0, 200) },
      });
    }
  }
}
