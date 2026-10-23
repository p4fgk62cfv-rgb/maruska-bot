import { ERROR_TEXT_RU } from '@arena/shared';
import type { FastifyInstance, FastifyRequest } from 'fastify';
import { z } from 'zod';
import { requireSession, sessionOf } from '../auth/plugin.js';
import type { Context } from '../context.js';
import type { Prisma } from '../generated/prisma/client.js';
import { AppError } from '../lib/errors.js';
import { displayName } from '../services/users.js';

/** How a game ended, in words. */
export const REASON_TEXT: Record<string, string> = {
  cards: 'остался с картами',
  last_attack: 'вышли одновременно — проиграл последний ходивший',
  timeout: 'время хода вышло',
  surrender: 'сдался',
  cancelled: 'партия отменена, ставки возвращены',
};

const CODE_TEXT: Record<string, string> = {
  CARD_DOES_NOT_BEAT: 'карта не бьёт',
  RANK_NOT_ON_TABLE: 'такого достоинства нет на столе',
  NOT_YOUR_TURN: 'не его ход',
  CANNOT_PASS: 'нельзя сказать «бито»',
  CANNOT_TAKE: 'нельзя взять',
  TABLE_FULL: 'на столе уже максимум карт',
  CARD_NOT_IN_HAND: 'такой карты нет в руке',
  NOT_IN_GAME: 'игрок уже не в партии',
  GAME_FINISHED: 'партия уже закончилась',
  RATE_LIMITED: 'слишком часто',
  SERVER_ERROR: 'ошибка сервера',
};

/** A refusal code in words: ours first, then the text the player saw. */
const codeText = (code: string): string =>
  CODE_TEXT[code] ?? ((ERROR_TEXT_RU as Record<string, string | undefined>)[code]?.replace(/\.$/, '').toLowerCase() || code);

const SUITS: Record<string, string> = { S: '♠', H: '♥', D: '♦', C: '♣' };
const card = (id: unknown) => (typeof id === 'string' ? id.slice(0, -1) + (SUITS[id.slice(-1)] ?? id.slice(-1)) : '?');

/** One move from game_moves, in words. */
export function moveText(action: Record<string, unknown>): string {
  switch (action.type) {
    case 'PLAY_CARD':
      return action.target !== undefined ? `бьёт ${card(action.card)}` : `ходит ${card(action.card)}`;
    case 'PLAY_CARDS':
      return `ходит ${Array.isArray(action.cards) ? action.cards.map(card).join(' ') : ''}`;
    case 'TRANSFER':
      return `переводит ${card(action.card)}`;
    case 'TAKE_CARDS':
      return 'берёт';
    case 'PASS':
      return 'бито / пас';
    case 'LEAVE_GAME':
      return 'сдался';
    case 'REPORT_CHEAT':
      return 'ловит шулера';
    case 'UNDO':
      return 'вернул карту';
    case 'TIMEOUT':
      return '⏰ время хода вышло';
    default:
      return String(action.type ?? '?');
  }
}

/** One journal event, in words. */
export function eventText(kind: string, details: Record<string, unknown> | null): string {
  const d = details ?? {};
  switch (kind) {
    case 'offline':
      return '📵 пропала связь';
    case 'online':
      return '📶 связь вернулась';
    case 'wait':
      return `⏳ ход ждёт игрока без связи (до ${d.seconds ?? '?'} с)`;
    case 'move_refused':
      return `🚫 ход отклонён: ${codeText(String(d.code))}${d.card ? ` (${Array.isArray(d.card) ? d.card.map(card).join(' ') : card(d.card)})` : ''}`;
    case 'tournament_table':
      return `🏆 стол ${d.round ?? '?'} турнира «${d.title ?? ''}»`;
    case 'cancelled':
      return `♻️ партия отменена (${d.why === 'restart' ? 'перезапуск сервера' : 'модератор'})`;
    case 'settlement_failed':
      return `💥 не удалось рассчитать партию: ${d.error ?? ''}`;
    case 'message_lost':
      return `✉️ сообщение в группу не доставлено (${d.outcome}): ${d.text ?? ''}`;
    case 'no_show':
      return `🪑 ${d.name ?? 'игрок'} не пришёл за стол ${d.round ?? ''}`;
    case 'forfeit':
      return `🚪 ${d.name ?? 'игрок'} ушёл из-за стола ${d.round ?? ''}`;
    case 'replay':
      return `♻️ стол ${d.round ?? ''} переигрывается: партия не доиграна`;
    default:
      return kind;
  }
}

/** What the owner should look at: kinds that point to a problem. */
const PROBLEM_KINDS = ['offline', 'wait', 'move_refused', 'cancelled', 'settlement_failed', 'message_lost', 'no_show', 'forfeit', 'replay'];

/**
 * «Журнал» in «Управление» (owners only): what happened in games and tournaments, so a complaint
 * («меня выкинуло», «карта не кинулась», «Мара не написала») can be looked up with its cause.
 */
export async function journalRoutes(app: FastifyInstance, ctx: Context): Promise<void> {
  const { db } = ctx;
  const auth = { preHandler: requireSession(ctx.config.SESSION_SECRET) };

  const owner = async (request: FastifyRequest): Promise<void> => {
    const user = await db.user.findUnique({ where: { id: sessionOf(request).sub }, select: { telegramId: true } });
    if (!user || !ctx.users.isOwnerTelegram(user.telegramId)) throw new AppError('FORBIDDEN');
  };

  const names = async (ids: Iterable<string>): Promise<Map<string, string>> => {
    const list = [...new Set(ids)].filter(Boolean);
    if (!list.length) return new Map();
    const users = await db.user.findMany({ where: { id: { in: list } }, include: { profile: { select: { nickname: true } } } });
    return new Map(users.map((u) => [u.id, u.profile?.nickname || displayName(u)]));
  };

  /** Problems over the last hours: counts and the latest items. */
  app.get('/owner/journal/summary', auth, async (request) => {
    await owner(request);
    const { hours } = z.object({ hours: z.coerce.number().int().min(1).max(720).default(24) }).parse(request.query);
    const since = new Date(Date.now() - hours * 3600_000);
    const [results, aborted, events, started, minis] = await Promise.all([
      db.gameResult.groupBy({ by: ['reason'], where: { createdAt: { gte: since } }, _count: { _all: true } }),
      db.game.count({ where: { startedAt: { gte: since }, status: 'ABORTED' } }),
      db.gameEvent.groupBy({ by: ['kind'], where: { createdAt: { gte: since } }, _count: { _all: true } }),
      db.game.count({ where: { startedAt: { gte: since } } }),
      db.miniTournament.count({ where: { createdAt: { gte: since } } }),
    ]);
    const refused = await db.gameEvent.findMany({ where: { createdAt: { gte: since }, kind: 'move_refused' }, select: { details: true } });
    const byCode = new Map<string, number>();
    for (const e of refused) {
      const code = String((e.details as { code?: string } | null)?.code ?? '?');
      byCode.set(code, (byCode.get(code) ?? 0) + 1);
    }
    const recent = await db.gameEvent.findMany({
      where: { createdAt: { gte: since }, kind: { in: PROBLEM_KINDS.filter((k) => k !== 'move_refused' && k !== 'offline') } },
      orderBy: { createdAt: 'desc' },
      take: 40,
    });
    const timeouts = await db.gameResult.findMany({
      where: { createdAt: { gte: since }, reason: { in: ['timeout', 'surrender'] } },
      orderBy: { createdAt: 'desc' },
      take: 20,
    });
    const who = await names([...recent.map((e) => e.userId ?? ''), ...timeouts.map((r) => r.loserId ?? '')]);
    const items = [
      ...recent.map((e) => ({
        at: e.createdAt.toISOString(),
        gameId: e.gameId,
        miniId: e.miniId,
        text: `${e.userId ? `${who.get(e.userId) ?? 'игрок'}: ` : ''}${eventText(e.kind, e.details as Record<string, unknown> | null)}`,
      })),
      ...timeouts.map((r) => ({
        at: r.createdAt.toISOString(),
        gameId: r.gameId,
        miniId: null,
        text: `${r.reason === 'timeout' ? '⏰' : '🏳️'} ${who.get(r.loserId ?? '') ?? 'игрок'} проиграл: ${REASON_TEXT[r.reason ?? ''] ?? r.reason}`,
      })),
    ].sort((a, b) => b.at.localeCompare(a.at));
    const count = (kind: string) => events.find((e) => e.kind === kind)?._count._all ?? 0;
    return {
      hours,
      games: started,
      tournaments: minis,
      endings: [
        ...results.map((r) => ({ reason: r.reason ?? 'draw', text: REASON_TEXT[r.reason ?? ''] ?? 'ничья', count: r._count._all })),
        ...(aborted ? [{ reason: 'aborted', text: 'прервана', count: aborted }] : []),
      ].sort((a, b) => b.count - a.count),
      problems: {
        offline: count('offline'),
        waits: count('wait'),
        refused: count('move_refused'),
        lostMessages: count('message_lost'),
        noShows: count('no_show'),
        forfeits: count('forfeit'),
        replays: count('replay'),
        cancelled: count('cancelled'),
        settlementFailed: count('settlement_failed'),
      },
      refusedByCode: [...byCode].map(([code, n]) => ({ code, text: codeText(code), count: n })).sort((a, b) => b.count - a.count),
      recent: items.slice(0, 50),
    };
  });

  /** Recent games, newest first; «problems» — only games with something to look at. */
  app.get('/owner/journal/games', auth, async (request) => {
    await owner(request);
    const q = z
      .object({ filter: z.enum(['all', 'problems', 'tournament']).default('all'), before: z.iso.datetime().optional(), limit: z.coerce.number().int().min(1).max(50).default(30) })
      .parse(request.query);
    const where: Prisma.GameWhereInput = { ...(q.before ? { startedAt: { lt: new Date(q.before) } } : {}) };
    if (q.filter === 'tournament') {
      const ids = await db.gameEvent.findMany({ where: { kind: 'tournament_table', gameId: { not: null } }, select: { gameId: true }, orderBy: { createdAt: 'desc' }, take: 500 });
      where.id = { in: ids.map((e) => e.gameId!) };
    }
    if (q.filter === 'problems') {
      const ids = await db.gameEvent.findMany({ where: { kind: { in: PROBLEM_KINDS }, gameId: { not: null } }, select: { gameId: true }, distinct: ['gameId'], orderBy: { createdAt: 'desc' }, take: 500 });
      where.OR = [{ id: { in: ids.map((e) => e.gameId!) } }, { result: { reason: { in: ['timeout', 'surrender', 'cancelled'] } } }, { status: 'ABORTED' }];
    }
    const games = await db.game.findMany({
      where,
      orderBy: { startedAt: 'desc' },
      take: q.limit,
      include: { players: { orderBy: { seat: 'asc' } }, result: true, room: { select: { maxPlayers: true, speed: true, variant: true } }, _count: { select: { moves: true } } },
    });
    const ids = games.map((g) => g.id);
    const events = ids.length ? await db.gameEvent.findMany({ where: { gameId: { in: ids } }, select: { gameId: true, kind: true, details: true } }) : [];
    const who = await names(games.flatMap((g) => g.players.map((p) => p.userId)));
    return games.map((g) => {
      const mine = events.filter((e) => e.gameId === g.id);
      const table = mine.find((e) => e.kind === 'tournament_table')?.details as { title?: string; round?: number } | undefined;
      const n = (kind: string) => mine.filter((e) => e.kind === kind).length;
      return {
        id: g.id,
        startedAt: g.startedAt.toISOString(),
        finishedAt: g.finishedAt?.toISOString() ?? null,
        status: g.status,
        durationMs: g.result?.durationMs ?? null,
        moves: g._count.moves,
        stake: Number(g.stake),
        players: g.players.map((p) => ({ name: who.get(p.userId) ?? 'игрок', outcome: p.outcome, place: p.place })),
        loser: g.result?.loserId ? (who.get(g.result.loserId) ?? 'игрок') : null,
        reason: g.result?.reason ?? (g.status === 'ABORTED' ? 'cancelled' : null),
        reasonText: g.result ? (REASON_TEXT[g.result.reason ?? ''] ?? 'ничья') : g.status === 'PLAYING' ? 'идёт' : 'прервана',
        tournament: table ? { title: table.title ?? '', round: table.round ?? null } : null,
        flags: { offline: n('offline'), waits: n('wait'), refused: n('move_refused'), cancelled: n('cancelled') + n('settlement_failed') },
      };
    });
  });

  /** One game, move by move, with everything that happened around the moves. */
  app.get('/owner/journal/games/:id', auth, async (request) => {
    await owner(request);
    const { id } = z.object({ id: z.uuid() }).parse(request.params);
    const game = await db.game.findUnique({
      where: { id },
      include: { players: { orderBy: { seat: 'asc' } }, result: true, moves: { orderBy: { seq: 'asc' } }, room: true },
    });
    if (!game) throw new AppError('NOT_FOUND');
    const events = await db.gameEvent.findMany({ where: { gameId: id }, orderBy: { createdAt: 'asc' } });
    const who = await names([...game.players.map((p) => p.userId), ...events.map((e) => e.userId ?? '')]);
    const t0 = game.startedAt.getTime();
    const timeline = [
      ...game.moves.map((m) => ({
        at: m.createdAt.toISOString(),
        sec: Math.round((m.createdAt.getTime() - t0) / 100) / 10,
        kind: 'move' as const,
        who: m.userId ? (who.get(m.userId) ?? 'игрок') : 'сервер',
        text: moveText(m.action as Record<string, unknown>),
      })),
      ...events.map((e) => ({
        at: e.createdAt.toISOString(),
        sec: Math.round((e.createdAt.getTime() - t0) / 100) / 10,
        kind: 'event' as const,
        who: e.userId ? (who.get(e.userId) ?? 'игрок') : '',
        text: eventText(e.kind, e.details as Record<string, unknown> | null),
        problem: PROBLEM_KINDS.includes(e.kind),
      })),
    ].sort((a, b) => a.at.localeCompare(b.at));
    const table = events.find((e) => e.kind === 'tournament_table')?.details as { title?: string; round?: number } | undefined;
    return {
      id: game.id,
      roomId: game.roomId,
      startedAt: game.startedAt.toISOString(),
      finishedAt: game.finishedAt?.toISOString() ?? null,
      status: game.status,
      rules: { players: game.room.maxPlayers, deck: game.room.deckSize, speed: game.room.speed, variant: game.room.variant, throwIn: game.room.throwIn, fairness: game.room.fairness, ending: game.room.ending },
      stake: Number(game.stake),
      tournament: table ? { title: table.title ?? '', round: table.round ?? null } : null,
      players: game.players.map((p) => ({ name: who.get(p.userId) ?? 'игрок', outcome: p.outcome, place: p.place })),
      loser: game.result?.loserId ? (who.get(game.result.loserId) ?? 'игрок') : null,
      reason: game.result?.reason ?? null,
      reasonText: game.result ? (REASON_TEXT[game.result.reason ?? ''] ?? 'ничья') : game.status === 'PLAYING' ? 'идёт' : 'прервана',
      durationMs: game.result?.durationMs ?? null,
      timeline,
    };
  });

  /** Group mini-tournaments: who took which place and why, every table and what went wrong. */
  app.get('/owner/journal/tournaments', auth, async (request) => {
    await owner(request);
    const { limit } = z.object({ limit: z.coerce.number().int().min(1).max(50).default(20) }).parse(request.query);
    const minis = await db.miniTournament.findMany({ orderBy: { createdAt: 'desc' }, take: limit, include: { players: true } });
    const ids = minis.map((m) => m.id);
    const events = ids.length ? await db.gameEvent.findMany({ where: { miniId: { in: ids } }, orderBy: { createdAt: 'asc' } }) : [];
    const gameIds = events.filter((e) => e.kind === 'tournament_table' && e.gameId).map((e) => e.gameId!);
    const results = gameIds.length ? await db.gameResult.findMany({ where: { gameId: { in: gameIds } } }) : [];
    const who = await names([...results.map((r) => r.loserId ?? ''), ...events.map((e) => e.userId ?? '')]);
    const OUT: Record<string, string> = { game: 'остался дураком', no_show: 'не пришёл за стол', left: 'ушёл из-за стола' };
    return minis.map((m) => {
      const mine = events.filter((e) => e.miniId === m.id);
      return {
        id: m.id,
        title: m.title,
        chatId: m.chatId.toString(),
        status: m.status,
        createdAt: m.createdAt.toISOString(),
        finishedAt: m.finishedAt?.toISOString() ?? null,
        players: m.players
          .map((p) => ({ name: p.name, place: p.place, round: p.outRound, why: p.outReason ? (OUT[p.outReason] ?? p.outReason) : m.winnerId === p.userId ? 'победитель' : null }))
          .sort((a, b) => (a.place ?? 99) - (b.place ?? 99)),
        tables: mine
          .filter((e) => e.kind === 'tournament_table')
          .map((e) => {
            const r = results.find((x) => x.gameId === e.gameId);
            return {
              gameId: e.gameId,
              round: (e.details as { round?: number } | null)?.round ?? null,
              at: e.createdAt.toISOString(),
              loser: r?.loserId ? (who.get(r.loserId) ?? 'игрок') : null,
              reason: r?.reason ?? null,
              reasonText: r ? (REASON_TEXT[r.reason ?? ''] ?? 'ничья') : 'не доиграна',
            };
          }),
        problems: mine
          .filter((e) => e.kind !== 'tournament_table')
          .map((e) => ({ at: e.createdAt.toISOString(), text: `${e.userId ? `${who.get(e.userId) ?? ''} ` : ''}${eventText(e.kind, e.details as Record<string, unknown> | null)}` })),
      };
    });
  });
}
