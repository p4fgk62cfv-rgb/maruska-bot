/** Prize split by final place, in percent of the pool. Heads-up single elimination. */
export function prizeShares(players: number): number[] {
  if (players >= 8) return [40, 25, 12.5, 12.5, 2.5, 2.5, 2.5, 2.5];
  if (players >= 4) return [50, 30, 10, 10];
  if (players >= 2) return [70, 30];
  return [100];
}

/** Places tied by the round of elimination: final loser 2nd, semi-final losers 3rd–4th, … */
export function placeForRound(rounds: number, eliminatedRound: number): number {
  return 2 ** (rounds - eliminatedRound) + 1;
}

/**
 * Splits the pool into whole credits per place. Players sharing a place share its shares
 * (3rd–4th each get their own 10%). Any rounding remainder goes to the winner.
 */
export function prizeAmounts(pool: number, players: number): number[] {
  const shares = prizeShares(players).slice(0, players);
  const amounts = shares.map((s) => Math.floor((pool * s) / 100));
  const rest = pool - amounts.reduce((a, b) => a + b, 0);
  if (amounts.length) amounts[0]! += rest;
  return amounts;
}

export function bracketSize(players: number): number {
  let size = 2;
  while (size < players) size *= 2;
  return size;
}
