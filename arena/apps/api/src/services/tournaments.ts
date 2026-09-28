import { randomInt } from 'node:crypto';
import {
  bracketSize,
  MODE_LABEL_RU,
  placeForRound,
  prizeAmounts,
  roomDeepLink,
  type GameResultDto,
  type TournamentDetailDto,
  type TournamentDto,
} from '@arena/shared';
import type { FastifyBaseLogger } from 'fastify';
import { z } from 'zod';
import type { Config } from '../config.js';
import type { Db } from '../db.js';
import type { Tournament, TournamentMatch } from '../generated/prisma/client.js';
import { AppError } from '../lib/errors.js';
import { inviteCode } from '../lib/ids.js';
import { toNumber } from '../lib/money.js';
import { SerialQueue } from '../lib/serial.js';
import type { Realtime } from '../realtime/realtime.js';
import type { Room } from '../realtime/types.js';
import type { Ledger } from './ledger.js';
import type { Outbox } from './notifier.js';
import { publicUser } from './users.js';

/** Rules of every match in a tournament. Two players, 36 cards. */
export const tournamentSettingsSchema = z.object({
  variant: z.enum(['podkidnoy', 'perevodnoy']).default('podkidnoy'),
  throwIn: z.enum(['all', 'neighbors']).default('all'),
  fairness: z.enum(['fair', 'cheaters']).default('fair'),
  ending: z.enum(['classic', 'draw']).default('classic'),
  speed: z.enum(['normal', 'fast']).default('normal'),
});
export type TournamentSettings = z.infer<typeof tournamentSettingsSchema>;

export const createTournamentSchema = z.object({
  title: z.string().min(3).max(80),
  entryFee: z.number().int().min(0).max(10_000_000),
  maxPlayers: z.union([z.literal(4), z.literal(8), z.literal(16), z.literal(32), z.literal(64)]),
  startsAt: z.coerce.date(),
  settings: tournamentSettingsSchema.default({ variant: 'podkidnoy', throwIn: 'all', fairness: 'fair', ending: 'classic', speed: 'normal' }),
});

const ACTIVE = ['ANNOUNCED', 'REGISTRATION', 'RUNNING'] as const;

/**
 * Heads-up single-elimination tournaments.
 *
 * REGISTRATION → (startsAt) RUNNING → FINISHED, or CANCELLED with refunds when fewer
 * than two joined. Everything that changes a tournament runs through one queue, and
 * `tick()` (every few seconds) is idempotent: it creates missing match rooms, recovers
 * after a restart and moves the bracket forward.
 */
export class TournamentService {
  private readonly queue = new SerialQueue();
  private timer: NodeJS.Timeout | null = null;

  constructor(
    private readonly deps: {
      config: Config;
      db: Db;
      ledger: Ledger;
      outbox: Outbox;
      realtime: Realtime;
      log: FastifyBaseLogger;
    },
  ) {
    deps.realtime.rooms.matchHooks = {
      finished: (room, result) => void this.queue.run(() => this.onGame(room, result)).catch((e) => this.fail(e)),
      noShow: (room, ready) => void this.queue.run(() => this.onNoShow(room, ready)).catch((e) => this.fail(e)),
      forfeit: (room, userId) => void this.queue.run(() => this.onForfeit(room, userId)).catch((e) => this.fail(e)),
    };
  }

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
    this.deps.log.error({ err: error }, 'tournament job failed');
  }

  // ── reading ────────────────────────────────────────────────

  async list(me: string, active: boolean): Promise<TournamentDto[]> {
    const rows = await this.db.tournament.findMany({
      where: { status: active ? { in: [...ACTIVE] } : { in: ['FINISHED', 'CANCELLED'] } },
      orderBy: { startsAt: active ? 'asc' : 'desc' },
      include: { _count: { select: { players: true } }, players: { where: { userId: me }, select: { userId: true } } },
      take: 50,
    });
    return rows.map((t) => this.dto(t, t._count.players, t.players.length > 0));
  }

  async detail(me: string, id: string): Promise<TournamentDetailDto> {
    const t = await this.db.tournament.findUnique({
      where: { id },
      include: { players: { include: { user: { include: { profile: true } } } }, matches: { orderBy: [{ round: 'asc' }, { slot: 'asc' }] } },
    });
    if (!t) throw new AppError('NOT_FOUND');
    const users = new Map(t.players.filter((p) => p.user.profile).map((p) => [p.userId, publicUser(p.user, p.user.profile!)]));
    const size = bracketSize(Math.max(2, t.players.length));
    return {
      ...this.dto(t, t.players.length, users.has(me)),
      rounds: Math.log2(size),
      prizes: prizeAmounts(toNumber(t.prizePool), Math.max(2, t.players.length)),
      entrants: t.players
        .filter((p) => users.has(p.userId))
        .map((p) => ({ ...users.get(p.userId)!, place: p.place, prize: p.prize === null ? null : toNumber(p.prize), eliminatedRound: p.eliminatedRound }))
        .sort((a, b) => (a.place ?? 999) - (b.place ?? 999)),
      matches: t.matches
        .filter((m) => users.has(m.playerA))
        .map((m) => ({
          id: m.id,
          round: m.round,
          slot: m.slot,
          a: users.get(m.playerA)!,
          b: m.playerB ? (users.get(m.playerB) ?? null) : null,
          winnerId: m.winnerId,
          status: m.status,
          decidedBy: m.decidedBy,
        })),
    };
  }

  private dto(t: Tournament, players: number, joined: boolean): TournamentDto {
    const s = tournamentSettingsSchema.parse(t.settings);
    return {
      id: t.id,
      title: t.title,
      status: t.status,
      prizePool: toNumber(t.prizePool),
      entryFee: toNumber(t.entryFee),
      currency: t.currency,
      players,
      maxPlayers: t.maxPlayers,
      startsAt: t.startsAt.toISOString(),
      joined,
      modes: [MODE_LABEL_RU[s.variant]!, MODE_LABEL_RU[s.throwIn]!, ...(s.fairness === 'cheaters' ? [MODE_LABEL_RU.cheaters!] : []), MODE_LABEL_RU[s.ending]!],
    };
  }

  // ── registration ───────────────────────────────────────────

  async create(input: z.infer<typeof createTournamentSchema>): Promise<string> {
    const t = await this.db.tournament.create({
      data: {
        title: input.title,
        status: 'REGISTRATION',
        entryFee: BigInt(input.entryFee),
        maxPlayers: input.maxPlayers,
        startsAt: input.startsAt,
        settings: input.settings,
      },
    });
    return t.id;
  }

  /** Entry fee goes into the prize pool in the same transaction as the registration. */
  async register(userId: string, id: string): Promise<void> {
    await this.queue.run(() =>
      this.db.$transaction(async (tx) => {
        const t = await tx.tournament.findUnique({ where: { id }, include: { _count: { select: { players: true } } } });
        if (!t || t.status !== 'REGISTRATION') throw new AppError('ROOM_CLOSED');
        if (await tx.tournamentPlayer.findUnique({ where: { tournamentId_userId: { tournamentId: id, userId } } })) return;
        if (t._count.players >= t.maxPlayers) throw new AppError('ROOM_FULL');
        if (t.entryFee > 0n) {
          await this.deps.ledger.postIn(tx, {
            userId,
            currency: t.currency,
            amount: -t.entryFee,
            type: 'TOURNAMENT_FEE',
            source: `tournament:${id}`,
            idempotencyKey: `tfee:${id}:${userId}:${Date.now()}`,
          });
        }
        await tx.tournamentPlayer.create({ data: { tournamentId: id, userId } });
        await tx.tournament.update({ where: { id }, data: { prizePool: { increment: t.entryFee } } });
      }),
    );
  }

  async unregister(userId: string, id: string): Promise<void> {
    await this.queue.run(() =>
      this.db.$transaction(async (tx) => {
        const t = await tx.tournament.findUnique({ where: { id } });
        if (!t || t.status !== 'REGISTRATION') throw new AppError('GAME_ALREADY_STARTED');
        const removed = await tx.tournamentPlayer.deleteMany({ where: { tournamentId: id, userId } });
        if (!removed.count) return;
        if (t.entryFee > 0n) {
          await this.deps.ledger.postIn(tx, {
            userId,
            currency: t.currency,
            amount: t.entryFee,
            type: 'TOURNAMENT_REFUND',
            source: `tournament:${id}`,
            idempotencyKey: `trefund:${id}:${userId}:${Date.now()}`,
          });
        }
        await tx.tournament.update({ where: { id }, data: { prizePool: { decrement: t.entryFee } } });
      }),
    );
  }

  // ── the clock ──────────────────────────────────────────────

  tick(now = new Date()): Promise<void> {
    return this.queue.run(async () => {
      const due = await this.db.tournament.findMany({ where: { status: { in: ['ANNOUNCED', 'REGISTRATION'] }, startsAt: { lte: now } } });
      for (const t of due) await this.begin(t);
      const running = await this.db.tournament.findMany({ where: { status: 'RUNNING' } });
      for (const t of running) {
        await this.advance(t.id);
        await this.openMatches(t.id);
      }
    });
  }

  private async begin(t: Tournament): Promise<void> {
    const players = await this.db.tournamentPlayer.findMany({ where: { tournamentId: t.id } });
    if (players.length < 2) {
      await this.cancel(t);
      return;
    }
    const ids = players.map((p) => p.userId);
    for (let i = ids.length - 1; i > 0; i--) {
      const j = randomInt(i + 1);
      [ids[i], ids[j]] = [ids[j]!, ids[i]!];
    }
    const size = bracketSize(ids.length);
    // Seat i meets seat size-1-i: byes (empty seats) are spread so two byes never meet.
    const seats: (string | null)[] = [...ids, ...Array<null>(size - ids.length).fill(null)];
    const matches = Array.from({ length: size / 2 }, (_, slot) => ({ a: seats[slot]!, b: seats[size - 1 - slot] ?? null, slot }));
    await this.db.$transaction(async (tx) => {
      const claimed = await tx.tournament.updateMany({ where: { id: t.id, status: { in: ['ANNOUNCED', 'REGISTRATION'] } }, data: { status: 'RUNNING' } });
      if (!claimed.count) return;
      for (const m of matches) {
        await tx.tournamentMatch.create({
          data: {
            tournamentId: t.id,
            round: 1,
            slot: m.slot,
            playerA: m.a,
            playerB: m.b,
            ...(m.b === null ? { status: 'DONE' as const, winnerId: m.a, decidedBy: 'bye' } : {}),
          },
        });
      }
    });
  }

  private async cancel(t: Tournament): Promise<void> {
    await this.db.$transaction(async (tx) => {
      const claimed = await tx.tournament.updateMany({ where: { id: t.id, status: { not: 'CANCELLED' } }, data: { status: 'CANCELLED', finishedAt: new Date() } });
      if (!claimed.count) return;
      if (t.entryFee === 0n) return;
      const players = await tx.tournamentPlayer.findMany({ where: { tournamentId: t.id } });
      for (const p of players) {
        await this.deps.ledger.postIn(tx, {
          userId: p.userId,
          currency: t.currency,
          amount: t.entryFee,
          type: 'TOURNAMENT_REFUND',
          source: `tournament:${t.id}`,
          idempotencyKey: `tcancel:${t.id}:${p.userId}`,
        });
      }
    });
  }

  /** Creates the room for every undecided match whose room is not alive (first time, or after a restart / draw). */
  private async openMatches(tournamentId: string): Promise<void> {
    const t = await this.db.tournament.findUniqueOrThrow({ where: { id: tournamentId } });
    const settings = tournamentSettingsSchema.parse(t.settings);
    const matches = await this.db.tournamentMatch.findMany({ where: { tournamentId, status: { not: 'DONE' } } });
    const rooms = this.deps.realtime.rooms;
    for (const m of matches) {
      if (!m.playerB) continue;
      if (m.roomId && rooms.get(m.roomId)) continue;
      let room: Room;
      try {
        room = await rooms.createMatchRoom(
          { id: t.id, title: t.title, round: m.round, matchId: m.id },
          [m.playerA, m.playerB],
          { ...settings, deckSize: 36 },
        );
      } catch (error) {
        // A player is still finishing another game: try again on the next tick.
        if (error instanceof AppError && error.code === 'ALREADY_IN_ROOM') continue;
        throw error;
      }
      await this.db.tournamentMatch.update({ where: { id: m.id }, data: { roomId: room.id, status: 'PLAYING' } });
      await this.announce(t, m, room);
    }
  }

  private async announce(t: Tournament, m: TournamentMatch, room: Room): Promise<void> {
    const hub = this.deps.realtime.hub;
    const link = roomDeepLink(this.deps.config.BOT_USERNAME, this.deps.config.MINI_APP_SHORT_NAME || null, room.id, inviteCode(room.id, this.deps.config.SESSION_SECRET));
    for (const userId of [m.playerA, m.playerB!]) {
      if (hub.isOnline(userId)) {
        hub.send(userId, { type: 'TOURNAMENT_MATCH', tournamentId: t.id, title: t.title, round: m.round, roomId: room.id });
      } else {
        await this.deps.outbox.enqueue(userId, 'tournament_match', {
          text: `🏆 <b>${t.title}</b>: ваш матч ${m.round}-го раунда начинается. Нажмите «Готов» в течение 90 секунд, иначе засчитается поражение.`,
          button: { text: '🎮 К столу', url: link },
        });
      }
    }
  }

  // ── match outcomes ─────────────────────────────────────────

  private async onGame(room: Room, result: GameResultDto | null): Promise<void> {
    const matchId = room.tournament?.matchId;
    if (!matchId || !result) return;
    if (result.kind === 'draw') {
      // No draws in a knockout: the same pair plays again.
      await this.db.tournamentMatch.update({ where: { id: matchId }, data: { roomId: null, status: 'PENDING', decidedBy: 'draw_replay' } });
      return;
    }
    const winner = room.seats.find((s) => s.userId !== result.loserId)?.userId;
    if (winner) await this.decide(matchId, winner, 'game', room.gameId);
  }

  private async onNoShow(room: Room, ready: string[]): Promise<void> {
    const matchId = room.tournament?.matchId;
    if (!matchId) return;
    const match = await this.db.tournamentMatch.findUniqueOrThrow({ where: { id: matchId } });
    // Whoever turned up wins; if nobody did, the higher seed (player A) goes through.
    const winner = ready.length === 1 ? ready[0]! : match.playerA;
    await this.decide(matchId, winner, 'no_show', null);
  }

  private async onForfeit(room: Room, userId: string): Promise<void> {
    const matchId = room.tournament?.matchId;
    if (!matchId) return;
    const other = room.seats.find((s) => s.userId !== userId)?.userId;
    if (other) await this.decide(matchId, other, 'forfeit', null);
  }

  private async decide(matchId: string, winnerId: string, how: string, gameId: string | null): Promise<void> {
    const match = await this.db.tournamentMatch.findUniqueOrThrow({ where: { id: matchId } });
    if (match.status === 'DONE') return;
    const loser = match.playerA === winnerId ? match.playerB : match.playerA;
    await this.db.$transaction(async (tx) => {
      await tx.tournamentMatch.update({ where: { id: matchId }, data: { status: 'DONE', winnerId, decidedBy: how, gameId } });
      if (loser) {
        await tx.tournamentPlayer.update({
          where: { tournamentId_userId: { tournamentId: match.tournamentId, userId: loser } },
          data: { eliminatedRound: match.round },
        });
      }
    });
    await this.advance(match.tournamentId);
    await this.openMatches(match.tournamentId);
  }

  /** When a round is complete: pair the winners for the next one, or finish with the champion. */
  private async advance(tournamentId: string): Promise<void> {
    const matches = await this.db.tournamentMatch.findMany({ where: { tournamentId }, orderBy: [{ round: 'asc' }, { slot: 'asc' }] });
    if (!matches.length) return;
    const round = Math.max(...matches.map((m) => m.round));
    const current = matches.filter((m) => m.round === round);
    if (current.some((m) => m.status !== 'DONE')) return;
    const winners = current.map((m) => m.winnerId!);
    if (winners.length === 1) {
      await this.finish(tournamentId, winners[0]!, round);
      return;
    }
    await this.db.tournamentMatch.createMany({
      data: Array.from({ length: winners.length / 2 }, (_, slot) => ({
        tournamentId,
        round: round + 1,
        slot,
        playerA: winners[slot * 2]!,
        playerB: winners[slot * 2 + 1]!,
      })),
      skipDuplicates: true,
    });
  }

  private async finish(tournamentId: string, champion: string, rounds: number): Promise<void> {
    await this.db.$transaction(async (tx) => {
      const t = await tx.tournament.findUniqueOrThrow({ where: { id: tournamentId } });
      const claimed = await tx.tournament.updateMany({ where: { id: tournamentId, status: 'RUNNING' }, data: { status: 'FINISHED', finishedAt: new Date() } });
      if (!claimed.count) return;
      const players = await tx.tournamentPlayer.findMany({ where: { tournamentId } });
      const placed = players
        .map((p) => ({ userId: p.userId, place: p.userId === champion ? 1 : placeForRound(rounds, p.eliminatedRound ?? 1) }))
        .sort((a, b) => a.place - b.place);
      const amounts = prizeAmounts(toNumber(t.prizePool), players.length);
      for (const [index, p] of placed.entries()) {
        const prize = amounts[index] ?? 0;
        await tx.tournamentPlayer.update({
          where: { tournamentId_userId: { tournamentId, userId: p.userId } },
          data: { place: p.place, prize: BigInt(prize) },
        });
        if (prize > 0) {
          await this.deps.ledger.postIn(tx, {
            userId: p.userId,
            currency: t.currency,
            amount: BigInt(prize),
            type: 'TOURNAMENT_PRIZE',
            source: `tournament:${tournamentId}`,
            idempotencyKey: `tprize:${tournamentId}:${p.userId}`,
          });
        }
      }
    });
  }
}
