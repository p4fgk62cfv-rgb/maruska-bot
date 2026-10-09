import {
  ALL_QUESTS,
  LOGIN_REWARDS,
  QUESTS_BONUS,
  QUESTS_BONUS_KEY,
  nextDayAt,
  nextLoginStep,
  previousDay,
  questDay,
  questsFor,
  type DailyDto,
  type DailySummaryDto,
  type QuestDto,
  type QuestGame,
  type Reward,
} from '@arena/shared';
import type { Db } from '../db.js';
import type { Prisma, TransactionType } from '../generated/prisma/client.js';
import { AppError } from '../lib/errors.js';
import type { Ledger } from './ledger.js';

type Tx = Prisma.TransactionClient;

/**
 * Daily quests (three a day, counted by the game settlement) and the login calendar
 * (one reward a Moscow day, seven days in a row). Every payout is guarded twice: a
 * conditional update that only one request can win, and a ledger idempotency key.
 */
export class DailyService {
  constructor(private readonly db: Db, private readonly ledger: Ledger) {}

  /** Called inside the settlement transaction for every real player of a finished game. */
  async onGame(tx: Tx, userId: string, game: QuestGame, now = Date.now()): Promise<void> {
    const day = questDay(now);
    for (const quest of questsFor(userId, day)) {
      const step = quest.step(game);
      if (step <= 0 && !quest.inARow) continue;
      const where = { userId_day_key: { userId, day, key: quest.key } };
      const row = await tx.dailyQuest.findUnique({ where });
      const before = row?.progress ?? 0;
      if (before >= quest.goal) continue;
      const progress = step > 0 ? Math.min(quest.goal, before + step) : 0;
      if (progress === before) continue;
      await tx.dailyQuest.upsert({ where, create: { userId, day, key: quest.key, progress }, update: { progress } });
    }
  }

  async get(userId: string, now = Date.now()): Promise<DailyDto> {
    const today = questDay(now);
    const yesterday = previousDay(today);
    const [rows, profile] = await Promise.all([
      this.db.dailyQuest.findMany({ where: { userId, day: { in: [today, yesterday] } } }),
      this.db.profile.findUnique({ where: { userId }, select: { loginDay: true, loginStep: true } }),
    ]);
    const row = (day: string, key: string) => rows.find((r) => r.day === day && r.key === key);
    const list = (day: string): QuestDto[] =>
      questsFor(userId, day).map((q) => {
        const r = row(day, q.key);
        return { key: q.key, title: q.title, goal: q.goal, reward: q.reward, progress: r?.progress ?? 0, claimed: Boolean(r?.claimedAt), day };
      });
    const quests = list(today);
    // Done late yesterday and not collected: still there to collect today.
    const leftover = list(yesterday).filter((q) => q.progress >= q.goal && !q.claimed);
    const bonusRow = row(today, QUESTS_BONUS_KEY);
    const loginDay = profile?.loginDay ?? null;
    const loginStep = profile?.loginStep ?? 0;
    const claimedToday = loginDay === today;
    const step = nextLoginStep(loginDay, loginStep, today);
    return {
      today,
      resetsAt: new Date(nextDayAt(now)).toISOString(),
      quests: [...leftover, ...quests],
      bonus: { reward: QUESTS_BONUS, done: quests.every((q) => q.progress >= q.goal), claimed: Boolean(bonusRow?.claimedAt) },
      calendar: { step, claimedToday, reset: !claimedToday && step === 1 && loginStep > 0 && loginStep < LOGIN_REWARDS.length, rewards: LOGIN_REWARDS },
    };
  }

  async summary(userId: string, now = Date.now()): Promise<DailySummaryDto> {
    const daily = await this.get(userId, now);
    const quests = daily.quests.filter((q) => q.progress >= q.goal && !q.claimed).length;
    const bonus = daily.bonus.done && !daily.bonus.claimed ? 1 : 0;
    return { claimable: quests + bonus + (daily.calendar.claimedToday ? 0 : 1) };
  }

  /** Today's calendar reward. */
  async claimLogin(userId: string, now = Date.now()): Promise<DailyDto> {
    const today = questDay(now);
    await this.db.$transaction(async (tx) => {
      const profile = await tx.profile.findUnique({ where: { userId }, select: { loginDay: true, loginStep: true } });
      if (!profile) throw new AppError('UNAUTHORIZED');
      if (profile.loginDay === today) throw new AppError('REWARD_CLAIMED');
      const step = nextLoginStep(profile.loginDay, profile.loginStep, today);
      // Only one of two parallel taps passes: the second finds the day already set.
      const won = await tx.profile.updateMany({
        where: { userId, OR: [{ loginDay: null }, { loginDay: { not: today } }] },
        data: { loginDay: today, loginStep: step },
      });
      if (won.count !== 1) throw new AppError('REWARD_CLAIMED');
      await this.pay(tx, userId, LOGIN_REWARDS[step - 1]!, 'LOGIN_REWARD', `login:${today}`, `login:${userId}:${today}`);
    });
    return this.get(userId, now);
  }

  /** A finished quest of today (or yesterday's left over), or the «all three» bonus. */
  async claimQuest(userId: string, day: string, key: string, now = Date.now()): Promise<DailyDto> {
    const today = questDay(now);
    if (day !== today && day !== previousDay(today)) throw new AppError('NOT_FOUND');
    let reward: Reward;
    let goal: number;
    if (key === QUESTS_BONUS_KEY) {
      if (day !== today) throw new AppError('NOT_FOUND');
      reward = QUESTS_BONUS;
      goal = 0;
    } else {
      const quest = questsFor(userId, day).find((q) => q.key === key);
      if (!quest) throw new AppError('NOT_FOUND');
      reward = quest.reward;
      goal = quest.goal;
    }
    await this.db.$transaction(async (tx) => {
      if (key === QUESTS_BONUS_KEY) {
        const keys = questsFor(userId, day).map((q) => q.key);
        const rows = await tx.dailyQuest.findMany({ where: { userId, day, key: { in: keys } } });
        const done = questsFor(userId, day).every((q) => (rows.find((r) => r.key === q.key)?.progress ?? 0) >= q.goal);
        if (!done) throw new AppError('REWARD_NOT_READY');
        // ON CONFLICT DO NOTHING: a parallel tap waits here instead of failing on the key.
        await tx.dailyQuest.createMany({ data: [{ userId, day, key, progress: 1 }], skipDuplicates: true });
      }
      const won = await tx.dailyQuest.updateMany({ where: { userId, day, key, claimedAt: null, progress: { gte: goal } }, data: { claimedAt: new Date(now) } });
      if (won.count !== 1) {
        const row = await tx.dailyQuest.findUnique({ where: { userId_day_key: { userId, day, key } } });
        throw new AppError(row?.claimedAt ? 'REWARD_CLAIMED' : 'REWARD_NOT_READY');
      }
      await this.pay(tx, userId, reward, 'QUEST_REWARD', `quest:${day}:${key}`, `quest:${userId}:${day}:${key}`);
    });
    return this.get(userId, now);
  }

  private async pay(tx: Tx, userId: string, reward: Reward, type: TransactionType, source: string, key: string): Promise<void> {
    if (reward.credits > 0) {
      await this.ledger.postIn(tx, { userId, currency: 'CREDITS', amount: BigInt(reward.credits), type, source, idempotencyKey: `${key}:c` });
    }
    if (reward.coins > 0) {
      await this.ledger.postIn(tx, { userId, currency: 'COINS', amount: BigInt(reward.coins), type, source, idempotencyKey: `${key}:m` });
    }
  }
}

/** Every quest key, for validating a claim request. */
export const QUEST_KEYS: ReadonlySet<string> = new Set([...ALL_QUESTS.map((q) => q.key), QUESTS_BONUS_KEY]);
