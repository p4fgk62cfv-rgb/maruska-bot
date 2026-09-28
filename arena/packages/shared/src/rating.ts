/**
 * Rating, leagues and the regular-player bonus. Pure functions shared by the API (which
 * awards rating) and the web app (which draws badges). All tuning numbers live in RATING.
 */

export const RATING = {
  /** Points per log2 of credits won, for a brand-new player. */
  base: 10,
  /** Rating at which gains are halved; the higher the rating, the smaller the gain. */
  softCap: 5_000,
  bonus: {
    min: 2,
    max: 30,
    cooldownMs: 20 * 3600_000,
    /** Not playing longer than this drops the multiplier back to `min`. */
    resetAfterMs: 44 * 3600_000,
  },
  levelsPerLeague: 16,
} as const;

export type PremiumFactor = 'self' | 'table' | 'none';

export interface GainInput {
  /** Net credits won in this game. */
  winnings: number;
  rating: number;
  /** Regular-player bonus multiplier applied to this win (1 when none). */
  multiplier?: number;
  /** 'self' — winner has premium (+100%), 'table' — someone else at the table has it (+50%). */
  premium?: PremiumFactor;
}

/**
 * Gain grows with log2 of the win: winning 1000 gives ~50% more than winning 100
 * (log2 1001 / log2 101 ≈ 1.5). It shrinks as rating grows: softCap / (softCap + rating).
 */
export function ratingGain({ winnings, rating, multiplier = 1, premium = 'none' }: GainInput): number {
  if (winnings <= 0) return 0;
  const raw = RATING.base * Math.log2(1 + winnings) * (RATING.softCap / (RATING.softCap + Math.max(0, rating)));
  const premiumFactor = premium === 'self' ? 2 : premium === 'table' ? 1.5 : 1;
  return Math.max(1, Math.round(raw * multiplier * premiumFactor));
}

export interface League {
  key: 'silver' | 'gold' | 'ruby' | 'emerald' | 'sapphire' | 'supreme';
  name: string;
  color: string;
}

export const LEAGUES: readonly League[] = [
  { key: 'silver', name: 'Серебряная', color: '#c0c6d4' },
  { key: 'gold', name: 'Золотая', color: '#f5c451' },
  { key: 'ruby', name: 'Рубиновая', color: '#e0115f' },
  { key: 'emerald', name: 'Изумрудная', color: '#34d399' },
  { key: 'sapphire', name: 'Сапфировая', color: '#3b82f6' },
  { key: 'supreme', name: 'Высшая', color: '#a855f7' },
];

const TOTAL_LEVELS = LEAGUES.length * RATING.levelsPerLeague;

/** Points needed for global level `i` (0-based). Each level costs a little more than the last. */
export function levelCost(i: number): number {
  return 100 + 10 * i;
}

export interface RatingBadge {
  league: League;
  leagueIndex: number;
  /** Levels completed inside the league, 0..16. */
  level: number;
  /** Every 4 levels turn into a star; the remainder is shown as bars. */
  stars: number;
  bars: number;
  /** Progress to the next level, 0..100. 100 at the very top. */
  percent: number;
}

export function ratingBadge(rating: number): RatingBadge {
  let remaining = Math.max(0, Math.floor(rating));
  let completed = 0;
  while (completed < TOTAL_LEVELS && remaining >= levelCost(completed)) {
    remaining -= levelCost(completed);
    completed++;
  }
  const top = completed >= TOTAL_LEVELS;
  const leagueIndex = Math.min(LEAGUES.length - 1, Math.floor(completed / RATING.levelsPerLeague));
  const level = top ? RATING.levelsPerLeague : completed - leagueIndex * RATING.levelsPerLeague;
  return {
    league: LEAGUES[leagueIndex]!,
    leagueIndex,
    level,
    stars: Math.floor(level / 4),
    bars: level % 4,
    percent: top ? 100 : Math.floor((remaining / levelCost(completed)) * 100),
  };
}

export interface BonusState {
  multiplier: number;
  lastBonusAt: number | null;
  lastPlayedAt: number | null;
  /** How many bonuses in a row were collected without a reset; drives the glow. */
  streak: number;
}

export const INITIAL_BONUS: BonusState = { multiplier: RATING.bonus.min, lastBonusAt: null, lastPlayedAt: null, streak: 0 };

/**
 * Called once per finished game. Once every 20 hours one win is multiplied; each collected
 * bonus raises the multiplier by one (up to ×30). A break longer than 44 hours resets it.
 */
export function settleBonus(state: BonusState, now: number, won: boolean): { applied: number; next: BonusState } {
  let { multiplier, streak } = state;
  if (state.lastPlayedAt !== null && now - state.lastPlayedAt > RATING.bonus.resetAfterMs) {
    multiplier = RATING.bonus.min;
    streak = 0;
  }
  const available = state.lastBonusAt === null || now - state.lastBonusAt >= RATING.bonus.cooldownMs;
  if (won && available) {
    return {
      applied: multiplier,
      next: { multiplier: Math.min(RATING.bonus.max, multiplier + 1), lastBonusAt: now, lastPlayedAt: now, streak: streak + 1 },
    };
  }
  return { applied: 1, next: { multiplier, lastBonusAt: state.lastBonusAt, lastPlayedAt: now, streak } };
}

export type Glow = 'none' | 'fire' | 'green' | 'blue' | 'purple';

/** Glow around the rating by bonus days: 7 — yellow-red, 14 — green, 21 — blue, 28 — purple. */
export function bonusGlow(streak: number): Glow {
  if (streak >= 28) return 'purple';
  if (streak >= 21) return 'blue';
  if (streak >= 14) return 'green';
  if (streak >= 7) return 'fire';
  return 'none';
}

export function isPremium(premiumUntil: number | null, now: number): boolean {
  return premiumUntil !== null && premiumUntil > now;
}
