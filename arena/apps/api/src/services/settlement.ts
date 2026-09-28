import type { GameState } from '@arena/game-engine';
import { settle } from '@arena/game-engine';
import type { GameResultDto } from '@arena/shared';
import { isPremium, ratingGain, settleBonus, type PremiumFactor } from '@arena/shared';
import type { Db } from '../db.js';
import type { Prisma } from '../generated/prisma/client.js';
import { AppError } from '../lib/errors.js';
import { progressAchievements } from './achievements.js';
import type { Ledger } from './ledger.js';

type Tx = Prisma.TransactionClient;

export interface StartInput {
  gameId: string;
  roomId: string;
  stake: number;
  state: GameState;
  initialDeck: string[];
}

export interface FinishInput {
  gameId: string;
  stake: number;
  state: GameState;
  startedAt: number;
  /** Transfers made by each player in this game (for «Мастер перевода»). */
  transfers: Record<string, number>;
}

/**
 * The database side of a game: stakes in, payouts out, statistics and rating.
 * Each step is one transaction and idempotent, so a retry after a crash is harmless.
 */
export class SettlementService {
  constructor(private readonly db: Db, private readonly ledger: Ledger, private readonly rakePercent: number) {}

  /** Creates the game record and escrows every stake. Throws INSUFFICIENT_FUNDS (with the user) if someone is short. */
  async start(input: StartInput): Promise<void> {
    const { state } = input;
    await this.db.$transaction(async (tx) => {
      await tx.game.create({
        data: {
          id: input.gameId,
          roomId: input.roomId,
          stake: BigInt(input.stake),
          settings: { ...state.rules },
          trumpCard: state.trump.card,
          initialDeck: input.initialDeck,
          players: { create: state.players.map((p) => ({ userId: p.id, seat: p.seat })) },
        },
      });
      for (const player of state.players) {
        try {
          await this.ledger.postIn(tx, {
            userId: player.id,
            currency: 'CREDITS',
            amount: -BigInt(input.stake),
            type: 'GAME_STAKE',
            source: `game:${input.gameId}`,
            idempotencyKey: `stake:${input.gameId}:${player.id}`,
          });
        } catch (error) {
          if (error instanceof AppError && error.code === 'INSUFFICIENT_FUNDS') throw new ShortOfFunds(player.id);
          throw error;
        }
      }
      await tx.room.update({ where: { id: input.roomId }, data: { status: 'PLAYING' } });
    });
  }

  /** Server crashed without a snapshot: give everyone their stake back. */
  async abort(gameId: string): Promise<void> {
    await this.db.$transaction(async (tx) => {
      const game = await tx.game.findUnique({ where: { id: gameId }, include: { players: true } });
      if (!game || game.status !== 'PLAYING') return;
      for (const p of game.players) {
        await this.ledger.postIn(tx, {
          userId: p.userId,
          currency: 'CREDITS',
          amount: game.stake,
          type: 'GAME_REFUND',
          source: `game:${gameId}`,
          idempotencyKey: `refund:${gameId}:${p.userId}`,
        });
      }
      await tx.game.update({ where: { id: gameId }, data: { status: 'ABORTED', finishedAt: new Date() } });
      await tx.room.update({ where: { id: game.roomId }, data: { status: 'CLOSED', closedAt: new Date() } });
    });
  }

  async finish(input: FinishInput): Promise<GameResultDto> {
    const { state, stake, gameId } = input;
    const result = state.result;
    if (!result) throw new Error('game is not finished');

    const ids = state.players.map((p) => p.id);
    const settlement = settle(result, ids, stake, this.rakePercent);
    const now = new Date();

    return this.db.$transaction(
      async (tx) => {
        // Only the first finisher settles; a retry sees FINISHED and just rebuilds the answer.
        const claimed = await tx.game.updateMany({ where: { id: gameId, status: 'PLAYING' }, data: { status: 'FINISHED', finishedAt: now } });
        if (claimed.count === 0) return this.loadResult(tx, gameId, stake);

        const profiles = await tx.profile.findMany({ where: { userId: { in: ids } } });
        const anyPremium = profiles.some((p) => isPremium(p.premiumUntil?.getTime() ?? null, now.getTime()));
        const season = await tx.season.findFirst({ where: { startsAt: { lte: now }, endsAt: { gt: now } } });

        const payouts: GameResultDto['payouts'] = [];
        for (const payout of settlement.payouts) {
          const player = state.players.find((p) => p.id === payout.playerId)!;
          const profile = profiles.find((p) => p.userId === payout.playerId)!;
          if (payout.credit > 0) {
            await this.ledger.postIn(tx, {
              userId: payout.playerId,
              currency: 'CREDITS',
              amount: BigInt(payout.credit),
              type: result.kind === 'draw' ? 'GAME_REFUND' : 'GAME_PAYOUT',
              source: `game:${gameId}`,
              idempotencyKey: `payout:${gameId}:${payout.playerId}`,
            });
          }

          const won = result.kind === 'loser' && payout.playerId !== result.loser;
          const lost = result.kind === 'loser' && payout.playerId === result.loser;
          const premium: PremiumFactor = isPremium(profile.premiumUntil?.getTime() ?? null, now.getTime())
            ? 'self'
            : anyPremium
              ? 'table'
              : 'none';
          const bonus = settleBonus(
            {
              multiplier: profile.bonusMultiplier,
              lastBonusAt: profile.bonusLastAt?.getTime() ?? null,
              lastPlayedAt: profile.lastPlayedAt?.getTime() ?? null,
              streak: profile.bonusStreak,
            },
            now.getTime(),
            won && payout.net > 0,
          );
          const gain = won ? ratingGain({ winnings: payout.net, rating: profile.rating, multiplier: bonus.applied, premium }) : 0;
          const winStreak = won ? profile.winStreak + 1 : result.kind === 'draw' ? profile.winStreak : 0;

          await tx.profile.update({
            where: { userId: payout.playerId },
            data: {
              rating: { increment: gain },
              totalWinnings: { increment: BigInt(Math.max(0, payout.net)) },
              gamesPlayed: { increment: 1 },
              gamesWon: { increment: won ? 1 : 0 },
              gamesLost: { increment: lost ? 1 : 0 },
              gamesDraw: { increment: result.kind === 'draw' ? 1 : 0 },
              winStreak,
              bestStreak: Math.max(profile.bestStreak, winStreak),
              bonusMultiplier: bonus.next.multiplier,
              bonusLastAt: bonus.next.lastBonusAt ? new Date(bonus.next.lastBonusAt) : null,
              bonusStreak: bonus.next.streak,
              lastPlayedAt: now,
              caughtCheating: { increment: state.cheaters.includes(payout.playerId) ? 1 : 0 },
            },
          });

          if (season && (gain > 0 || payout.net > 0)) {
            await tx.seasonRating.upsert({
              where: { seasonId_userId: { seasonId: season.id, userId: payout.playerId } },
              create: { seasonId: season.id, userId: payout.playerId, rating: gain, wins: won ? 1 : 0, winnings: BigInt(Math.max(0, payout.net)) },
              update: { rating: { increment: gain }, wins: { increment: won ? 1 : 0 }, winnings: { increment: BigInt(Math.max(0, payout.net)) } },
            });
          }

          const outcome = result.kind === 'draw' ? 'DRAW' : won ? 'WIN' : result.reason === 'surrender' || result.reason === 'timeout' ? 'LEFT' : 'LOSS';
          await tx.gamePlayer.update({
            where: { gameId_userId: { gameId, userId: payout.playerId } },
            data: { place: player.place, outcome, payout: BigInt(payout.credit), net: BigInt(payout.net), ratingGain: gain },
          });
          await this.progressAchievements(tx, payout.playerId, gameId, {
            won,
            players: state.players.length,
            stake,
            transfers: input.transfers[payout.playerId] ?? 0,
          });

          payouts.push({ userId: payout.playerId, net: payout.net, place: player.place, ratingGain: gain, bonusMultiplier: bonus.applied });
        }

        await tx.gameResult.create({
          data: {
            gameId,
            kind: result.kind,
            reason: result.kind === 'loser' ? result.reason : null,
            winnerId: state.winner,
            loserId: state.loser,
            pot: BigInt(stake * ids.length),
            rake: BigInt(settlement.rake),
            durationMs: now.getTime() - input.startedAt,
          },
        });
        const game = await tx.game.findUniqueOrThrow({ where: { id: gameId } });
        await tx.room.update({ where: { id: game.roomId }, data: { status: 'FINISHED', closedAt: now } });

        return {
          kind: result.kind,
          reason: result.kind === 'loser' ? result.reason : null,
          loserId: state.loser,
          winnerId: state.winner,
          payouts,
          stake,
        };
      },
      { timeout: 20_000 },
    );
  }

  private async loadResult(tx: Tx, gameId: string, stake: number): Promise<GameResultDto> {
    const [result, players] = await Promise.all([
      tx.gameResult.findUnique({ where: { gameId } }),
      tx.gamePlayer.findMany({ where: { gameId } }),
    ]);
    return {
      kind: result?.kind === 'draw' ? 'draw' : 'loser',
      reason: (result?.reason as GameResultDto['reason']) ?? null,
      loserId: result?.loserId ?? null,
      winnerId: result?.winnerId ?? null,
      payouts: players.map((p) => ({
        userId: p.userId,
        net: Number(p.net ?? 0n),
        place: p.place,
        ratingGain: p.ratingGain ?? 0,
        bonusMultiplier: 1,
      })),
      stake,
    };
  }

  private async progressAchievements(
    tx: Tx,
    userId: string,
    gameId: string,
    game: { won: boolean; players: number; stake: number; transfers: number },
  ): Promise<void> {
    const profile = await tx.profile.findUniqueOrThrow({ where: { userId } });
    const absolute: Record<string, number> = {
      first_game: profile.gamesPlayed,
      first_win: profile.gamesWon,
      wins_10: profile.gamesWon,
      wins_100: profile.gamesWon,
      wins_1000: profile.gamesWon,
      streak_5: profile.bestStreak,
      streak_10: profile.bestStreak,
    };
    if (game.players === 6) absolute.full_table = 1;
    if (game.stake >= 1_000_000) absolute.high_roller = 1;
    await progressAchievements(tx, this.ledger, userId, `game:${gameId}`, absolute, game.transfers ? { transfer_master: game.transfers } : {});
  }
}

export class ShortOfFunds extends Error {
  constructor(public readonly userId: string) {
    super('INSUFFICIENT_FUNDS');
  }
}
