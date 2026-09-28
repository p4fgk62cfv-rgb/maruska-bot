import type { Prisma } from '../generated/prisma/client.js';
import type { Ledger } from './ledger.js';

type Tx = Prisma.TransactionClient;

/**
 * Progress for achievements. `absolute` values replace the progress when larger (wins so far),
 * `additive` values are added (transfers made this game). Unlocking pays the reward once,
 * guarded by the ledger idempotency key `ach:<user>:<key>`.
 */
export async function progressAchievements(
  tx: Tx,
  ledger: Ledger,
  userId: string,
  source: string,
  absolute: Record<string, number>,
  additive: Record<string, number> = {},
): Promise<string[]> {
  const keys = [...Object.keys(absolute), ...Object.keys(additive)];
  if (!keys.length) return [];
  const achievements = await tx.achievement.findMany({ where: { key: { in: keys } }, include: { users: { where: { userId } } } });
  const unlockedNow: string[] = [];
  for (const a of achievements) {
    const current = a.users[0];
    if (current?.unlockedAt) continue;
    const progress = a.key in additive ? (current?.progress ?? 0) + additive[a.key]! : Math.max(current?.progress ?? 0, absolute[a.key] ?? 0);
    const unlocked = progress >= a.goal;
    await tx.userAchievement.upsert({
      where: { userId_achievementId: { userId, achievementId: a.id } },
      create: { userId, achievementId: a.id, progress: Math.min(progress, a.goal), unlockedAt: unlocked ? new Date() : null },
      update: { progress: Math.min(progress, a.goal), unlockedAt: unlocked ? new Date() : null },
    });
    if (!unlocked) continue;
    unlockedNow.push(a.key);
    if (a.reward > 0n) {
      await ledger.postIn(tx, {
        userId,
        currency: a.currency,
        amount: a.reward,
        type: 'ACHIEVEMENT_REWARD',
        source,
        idempotencyKey: `ach:${userId}:${a.key}`,
      });
    }
  }
  return unlockedNow;
}
