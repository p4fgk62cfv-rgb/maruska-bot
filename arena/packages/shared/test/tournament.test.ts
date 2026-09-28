import { describe, expect, it } from 'vitest';
import { bracketSize, placeForRound, prizeAmounts } from '../src/tournament.js';

describe('tournament maths', () => {
  it('pays out the whole pool, remainder to the winner', () => {
    for (const [pool, n] of [[1000, 2], [999, 4], [12_345, 8], [7, 3]] as const) {
      const amounts = prizeAmounts(pool, n);
      expect(amounts.reduce((a, b) => a + b, 0)).toBe(pool);
      expect(amounts.every((a, i) => i === 0 || a <= amounts[0]!)).toBe(true);
    }
    expect(prizeAmounts(1000, 4)).toEqual([500, 300, 100, 100]);
  });

  it('brackets and places', () => {
    expect([2, 3, 4, 5, 9].map(bracketSize)).toEqual([2, 4, 4, 8, 16]);
    // 8-player bracket = 3 rounds: final loser 2nd, semi 3rd, quarter 5th.
    expect([3, 2, 1].map((r) => placeForRound(3, r))).toEqual([2, 3, 5]);
  });
});
