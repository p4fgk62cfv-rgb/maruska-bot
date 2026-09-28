import { describe, expect, it } from 'vitest';
import { bonusGlow, INITIAL_BONUS, levelCost, RATING, ratingBadge, ratingGain, settleBonus } from '../src/rating.js';

const H = 3600_000;

describe('rating gain', () => {
  it('winning 1000 raises rating ~50% more than winning 100', () => {
    const exact = (w: number) => RATING.base * Math.log2(1 + w);
    expect(exact(1000) / exact(100)).toBeCloseTo(1.5, 1);
    expect(ratingGain({ winnings: 1000, rating: 0 }) / ratingGain({ winnings: 100, rating: 0 })).toBeCloseTo(1.5, 1);
  });

  it('the same win is worth less at a higher rating', () => {
    expect(ratingGain({ winnings: 1000, rating: 20_000 })).toBeLessThan(ratingGain({ winnings: 1000, rating: 0 }));
  });

  it('applies the bonus multiplier and premium', () => {
    const raw = RATING.base * Math.log2(1001);
    expect(ratingGain({ winnings: 1000, rating: 0, multiplier: 3 })).toBe(Math.round(raw * 3));
    expect(ratingGain({ winnings: 1000, rating: 0, premium: 'self' })).toBe(Math.round(raw * 2));
    expect(ratingGain({ winnings: 1000, rating: 0, premium: 'table' })).toBe(Math.round(raw * 1.5));
    expect(ratingGain({ winnings: 0, rating: 0 })).toBe(0);
  });
});

describe('leagues', () => {
  it('starts in silver with no marks', () => {
    expect(ratingBadge(0)).toMatchObject({ leagueIndex: 0, level: 0, stars: 0, bars: 0, percent: 0 });
  });

  it('turns 4 bars into a star and moves to the next league after 16 levels', () => {
    let points = 0;
    for (let i = 0; i < 5; i++) points += levelCost(i);
    expect(ratingBadge(points)).toMatchObject({ level: 5, stars: 1, bars: 1 });
    points = 0;
    for (let i = 0; i < 16; i++) points += levelCost(i);
    expect(ratingBadge(points)).toMatchObject({ leagueIndex: 1, level: 0 });
    expect(ratingBadge(points).league.name).toBe('Золотая');
    expect(ratingBadge(10_000_000)).toMatchObject({ leagueIndex: 5, level: 16, stars: 4, percent: 100 });
  });
});

describe('regular-player bonus', () => {
  it('grows by one per collected bonus, at most once per 20 hours, up to ×30', () => {
    let state = INITIAL_BONUS;
    let r = settleBonus(state, 0, true);
    expect(r.applied).toBe(2);
    state = r.next;
    r = settleBonus(state, 10 * H, true);
    expect(r.applied).toBe(1);
    state = r.next;
    r = settleBonus(state, 21 * H, true);
    expect(r.applied).toBe(3);
    state = { ...r.next, multiplier: 30 };
    r = settleBonus(state, 42 * H, true);
    expect(r.next.multiplier).toBe(30);
  });

  it('resets after more than 44 hours without games', () => {
    const state = { multiplier: 12, lastBonusAt: 0, lastPlayedAt: 0, streak: 10 };
    const r = settleBonus(state, 45 * H, true);
    expect(r.applied).toBe(2);
    expect(r.next.streak).toBe(1);
  });

  it('glows by streak', () => {
    expect([0, 7, 14, 21, 28].map(bonusGlow)).toEqual(['none', 'fire', 'green', 'blue', 'purple']);
  });
});
