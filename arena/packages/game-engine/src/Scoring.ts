import type { GameResult, PlayerId } from './GameState.js';

export interface Payout {
  playerId: PlayerId;
  /** Amount credited back from escrow (stake already debited at game start). */
  credit: number;
  /** Net change versus before the game: credit - stake. */
  net: number;
}

export interface Settlement {
  payouts: Payout[];
  /** House commission taken from the fool's stake. */
  rake: number;
}

/**
 * Every player escrows `stake` when the game starts. The fool loses the stake;
 * the house keeps `rakePercent` of it and the rest is split evenly between the others.
 * A draw refunds everyone. Integer maths only: any indivisible remainder goes to the house.
 */
export function settle(result: GameResult, playerIds: PlayerId[], stake: number, rakePercent: number): Settlement {
  if (!Number.isSafeInteger(stake) || stake < 0) throw new Error('INVALID_STAKE');
  if (rakePercent < 0 || rakePercent > 100) throw new Error('INVALID_RAKE');

  if (result.kind === 'draw' || stake === 0) {
    return { payouts: playerIds.map((playerId) => ({ playerId, credit: stake, net: 0 })), rake: 0 };
  }

  const winners = playerIds.filter((id) => id !== result.loser);
  const rakeFromStake = Math.floor((stake * rakePercent) / 100);
  const share = Math.floor((stake - rakeFromStake) / winners.length);
  const rake = stake - share * winners.length;

  const payouts = playerIds.map((playerId) => {
    const credit = playerId === result.loser ? 0 : stake + share;
    return { playerId, credit, net: credit - stake };
  });
  return { payouts, rake };
}
