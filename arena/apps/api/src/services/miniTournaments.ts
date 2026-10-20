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
export const MINI_MAX_PLAYERS = 6;

const person = z.object({ telegramId: z.coerce.bigint(), name: z.string().min(1).max(128), username: z.string().max(64).nullish() });

/** Правила стола и сколько ждать у стола — их задают в админке Мары. */
export const miniRulesSchema = z.object({
  variant: z.enum(['podkidnoy', 'perevodnoy']).default(MINI_SETTINGS.variant),
  throwIn: z.enum(['all', 'neighbors']).default(MINI_SETTINGS.throwIn),
  speed: z.enum(['normal', 'fast']).default(MINI_SETTINGS.speed),
  readySeconds: z.number().int().min(15).max(600).optional(),
});
export type MiniRules = z.infer<typeof miniRulesSchema>;

export const startMiniSchema = z.object({
  chatId: z.coerce.bigint(),
  title: z.string().min(3).max(128).default('Мини-турнир'),
  prize: z.number().int().min(0).max(1_000_000_000),
  organizer: person,
  players: z.array(person).min(MINI_MIN_PLAYERS).max(MINI_MAX_PLAYERS),
  rules: miniRulesSchema.default({ variant: MINI_SETTINGS.variant, throwIn: MINI_SETTINGS.throwIn, speed: MINI_SETTINGS.speed }),
});
export type StartMini = z.infer<typeof startMiniSchema>;

type Player = MiniTournamentPlayer;

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
    const busy = await this.db.miniTournament.count({ where: { chatId: input.chatId, status: 'RUNNING' } });
    // В группе уже идёт мини-турнир: второй не начинаем.
    if (busy) throw new AppError('DUPLICATE_REQUEST');

    const users: string[] = [];
    for (const p of input.players) users.push(await this.account(p));

    const mini = await this.db.miniTournament.create({
      data: {
        chatId: input.chatId,
        title: input.title,
        prize: BigInt(input.prize),
        organizerTelegramId: input.organizer.telegramId,
        organizerName: input.organizer.name.slice(0, 128),
        settings: input.rules,
        players: {
          create: input.players.map((p, seat) => ({ userId: users[seat]!, telegramId: p.telegramId, name: p.name.slice(0, 128), seat })),
        },
      },
    });
    await this.queue.run(() => this.openTable(mini.id));
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
      const mini = await this.db.miniTournament.findFirst({ where: { chatId, status: 'RUNNING' } });
      if (!mini) return false;
      await this.db.miniTournament.update({ where: { id: mini.id }, data: { status: 'CANCELLED', finishedAt: new Date() } });
      await this.closeRoom(mini.roomId);
      await this.say(mini, `🛑 <b>${escapeHtml(mini.title)}</b> отменён организатором.`);
      return true;
    });
  }

  async active(chatId: bigint): Promise<{ id: string; round: number; players: { name: string; out: boolean }[] } | null> {
    const mini = await this.db.miniTournament.findFirst({ where: { chatId, status: 'RUNNING' }, include: { players: { orderBy: { seat: 'asc' } } } });
    if (!mini) return null;
    return { id: mini.id, round: mini.round, players: mini.players.map((p) => ({ name: p.name, out: p.outRound !== null })) };
  }

  private async tick(): Promise<void> {
    await this.queue.run(async () => {
      const running = await this.db.miniTournament.findMany({ where: { status: 'RUNNING' } });
      const rooms = this.deps.realtime.rooms;
      for (const mini of running) {
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
    const left = this.alive(mini.players);
    if (left.length === 1) {
      await this.finish(mini, left[0]!);
      return;
    }
    if (left.length === 0) {
      await this.db.miniTournament.update({ where: { id: mini.id }, data: { status: 'CANCELLED', finishedAt: new Date() } });
      await this.say(mini, `🛑 <b>${escapeHtml(mini.title)}</b>: за стол никто не пришёл — турнир закрыт без победителя.`);
      return;
    }
    const round = mini.round + 1;
    const rules = this.rules(mini);
    let room: Room;
    try {
      room = await this.deps.realtime.rooms.createMatchRoom(
        { id: mini.id, title: mini.title, round, matchId: mini.id, kind: 'mini', readyMs: this.seconds(mini) * 1000 },
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
    await this.say(
      mini,
      `🃏 <b>${escapeHtml(mini.title)}</b> · стол ${round} на ${left.length} ${left.length >= 5 ? 'игроков' : 'игрока'}\n\n` +
        `${left.map(mention).join(', ')}\n\n` +
        `Заходите за стол — ${seconds} с. Партия начнётся сама, когда сядут все. Кто не придёт — техническое поражение.`,
      { text: '🎮 За стол', url: link },
    );
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
    const rows = await this.db.miniTournament.findMany({ orderBy: { createdAt: 'desc' }, take: 30, include: { players: { orderBy: { seat: 'asc' } } } });
    return rows.map((m) => ({
      id: m.id,
      chatId: m.chatId.toString(),
      status: m.status,
      round: m.round,
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
        await this.say(mini, '♻️ Партия не доиграна — переигрываем тем же составом.');
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
        `💥 Стол ${mini.round} окончен. Дураком остался ${mention(loser)} — <b>${place} место</b>.\n` +
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
      const seconds = this.seconds(mini);
      await this.say(
        mini,
        `⏰ Не пришли за стол за ${seconds} с — техническое поражение: ${absent
          .map((p, i) => `${mention(p)} (${place - i} место)`)
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
      await this.say(mini, `🚪 ${mention(player)} ушёл из-за стола — техническое поражение, <b>${place} место</b>.`);
      // Стол закрывается вместе с уходом: остальных сажаем за новый.
      await this.db.miniTournament.update({ where: { id: mini.id }, data: { roomId: null } });
      await this.openTable(mini.id, true);
    });
  }

  private async current(room: Room): Promise<(MiniTournament & { players: Player[] }) | null> {
    const id = room.tournament?.kind === 'mini' ? room.tournament.id : null;
    if (!id) return null;
    const mini = await this.db.miniTournament.findUnique({ where: { id }, include: { players: true } });
    // Устаревший стол (уже пересоздан или турнир закрыт) ничего не решает.
    if (!mini || mini.status !== 'RUNNING' || mini.roomId !== room.id) return null;
    return mini;
  }

  /** Выбывают: место — по числу оставшихся (несколько сразу — по порядку записи, с конца). */
  private async out(mini: MiniTournament & { players: Player[] }, players: Player[], reason: string, place: number): Promise<void> {
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

  private async finish(mini: MiniTournament & { players: Player[] }, winner: Player): Promise<void> {
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

  private async say(mini: Pick<MiniTournament, 'chatId'>, text: string, button?: { text: string; url: string }): Promise<void> {
    const outcome = await this.deps.bot.send(mini.chatId, button ? { text, button } : { text });
    if (outcome !== 'ok') this.deps.log.warn({ chatId: mini.chatId.toString(), outcome }, 'mini-tournament message not delivered');
  }
}
