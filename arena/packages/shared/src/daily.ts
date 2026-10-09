/**
 * Daily quests and the login calendar. The server is the only one that counts and pays;
 * the client uses the same table to draw the cards.
 *
 * A «day» is a calendar day in Moscow time: the players live there, and a day that turns
 * at 3 a.m. their time would be confusing.
 */

export interface Reward {
  credits: number;
  coins: number;
}

/** What one finished game tells the quests about one player. */
export interface QuestGame {
  won: boolean;
  /** Bet credits (not a practice table). */
  stake: number;
  variant: 'podkidnoy' | 'perevodnoy';
  players: number;
  transfers: number;
}

export interface QuestDef {
  key: string;
  title: string;
  goal: number;
  reward: Reward;
  /** How much this game moves the quest. */
  step: (game: QuestGame) => number;
  /** A loss sets the progress back to zero («подряд»). */
  inARow?: boolean;
}

const tier = (credits: number, coins = 0): Reward => ({ credits, coins });

/** One quest of each tier a day: light, medium, hard. */
export const QUEST_TIERS: readonly (readonly QuestDef[])[] = [
  [
    { key: 'play_3', title: 'Сыграйте 3 партии', goal: 3, reward: tier(1_000), step: () => 1 },
    { key: 'play_podkidnoy_2', title: 'Сыграйте 2 партии в подкидного', goal: 2, reward: tier(1_000), step: (g) => (g.variant === 'podkidnoy' ? 1 : 0) },
    { key: 'play_perevodnoy_2', title: 'Сыграйте 2 партии в переводного', goal: 2, reward: tier(1_000), step: (g) => (g.variant === 'perevodnoy' ? 1 : 0) },
  ],
  [
    { key: 'win_2', title: 'Выиграйте 2 партии', goal: 2, reward: tier(2_000), step: (g) => (g.won ? 1 : 0) },
    { key: 'transfer_3', title: 'Переведите атаку 3 раза', goal: 3, reward: tier(2_000), step: (g) => g.transfers },
    { key: 'table_3', title: 'Сыграйте партию втроём или больше', goal: 1, reward: tier(2_000), step: (g) => (g.players >= 3 ? 1 : 0) },
  ],
  [
    { key: 'win_stake', title: 'Выиграйте партию на кредиты', goal: 1, reward: tier(3_000, 3), step: (g) => (g.won && g.stake > 0 ? 1 : 0) },
    { key: 'win_row_2', title: 'Выиграйте 2 партии подряд', goal: 2, reward: tier(3_000, 3), step: (g) => (g.won ? 1 : 0), inARow: true },
    { key: 'play_8', title: 'Сыграйте 8 партий', goal: 8, reward: tier(3_000, 3), step: () => 1 },
  ],
];

export const ALL_QUESTS: readonly QuestDef[] = QUEST_TIERS.flat();

/** Paid once all three quests of the day are done. */
export const QUESTS_BONUS: Reward = { credits: 0, coins: 10 };
/** Key of the bonus in the quest records. */
export const QUESTS_BONUS_KEY = 'all_done';

/** Seven days in a row; the seventh is the chest, then the week starts again. A missed day starts over. */
export const LOGIN_REWARDS: readonly Reward[] = [
  { credits: 500, coins: 0 },
  { credits: 1_000, coins: 0 },
  { credits: 0, coins: 5 },
  { credits: 2_000, coins: 0 },
  { credits: 3_000, coins: 0 },
  { credits: 0, coins: 10 },
  { credits: 5_000, coins: 20 },
];

const MOSCOW_MS = 3 * 3600_000;

/** «2026-10-03» — the Moscow calendar day of a moment. */
export function questDay(at: number = Date.now()): string {
  return new Date(at + MOSCOW_MS).toISOString().slice(0, 10);
}

/** The day before a `questDay`. */
export function previousDay(day: string): string {
  return new Date(Date.parse(`${day}T00:00:00Z`) - 24 * 3600_000).toISOString().slice(0, 10);
}

/** When the next Moscow day begins (new quests, the next calendar reward). */
export function nextDayAt(at: number = Date.now()): number {
  return Date.parse(`${questDay(at)}T00:00:00Z`) + 24 * 3600_000 - MOSCOW_MS;
}

/** The three quests of a player on a day: the same all day, different for different players. */
export function questsFor(userId: string, day: string): QuestDef[] {
  let h = 2166136261;
  for (const ch of `${userId}:${day}`) h = Math.imul(h ^ ch.charCodeAt(0), 16777619) >>> 0;
  return QUEST_TIERS.map((list, i) => list[(h >>> (i * 4)) % list.length]!);
}

/** The calendar step (1–7) today's claim gives, after the last claimed day and its step. */
export function nextLoginStep(lastDay: string | null, lastStep: number, today: string): number {
  if (lastDay === today) return lastStep;
  if (lastDay === previousDay(today) && lastStep >= 1 && lastStep < LOGIN_REWARDS.length) return lastStep + 1;
  return 1;
}

export interface QuestDto {
  key: string;
  title: string;
  goal: number;
  progress: number;
  reward: Reward;
  claimed: boolean;
  /** Done yesterday and not collected: still collectable today. */
  day: string;
}

export interface DailyDto {
  today: string;
  /** Next day (new quests, next calendar reward) begins at. */
  resetsAt: string;
  quests: QuestDto[];
  bonus: { reward: Reward; done: boolean; claimed: boolean };
  calendar: {
    /** 1–7: the step today's reward is (or was) for. */
    step: number;
    claimedToday: boolean;
    /** The run of days was broken: the week started over. */
    reset: boolean;
    rewards: readonly Reward[];
  };
}

/** Rewards to collect right now, for the badge on the home screen. */
export interface DailySummaryDto {
  claimable: number;
}
