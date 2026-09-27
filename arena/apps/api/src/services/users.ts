import { DAILY_CREDITS, RATING, type MeDto, type PublicUserDto, type WalletDto } from '@arena/shared';
import type { Db } from '../db.js';
import type { Currency, Profile, User } from '../generated/prisma/client.js';
import { toNumber } from '../lib/money.js';
import type { TelegramUser } from '../telegram/initData.js';
import type { Ledger } from './ledger.js';

export function isBanned(user: Pick<User, 'bannedAt' | 'bannedUntil'>, now = new Date()): boolean {
  return user.bannedAt !== null && (user.bannedUntil === null || user.bannedUntil > now);
}

const CURRENCIES: Currency[] = ['CREDITS', 'COINS', 'DIAMONDS'];

export function displayName(user: Pick<User, 'firstName' | 'lastName' | 'username'>): string {
  return [user.firstName, user.lastName].filter(Boolean).join(' ').trim() || user.username || 'Игрок';
}

export class UserService {
  constructor(private readonly db: Db, private readonly ledger: Ledger, private readonly signupBonus: number) {}

  /** Creates or refreshes the account from verified Telegram data. Safe to call on every login. */
  async upsertFromTelegram(tg: TelegramUser): Promise<User> {
    const fields = {
      username: tg.username ?? null,
      firstName: tg.first_name.slice(0, 128),
      lastName: tg.last_name?.slice(0, 128) ?? null,
      photoUrl: tg.photo_url ?? null,
      languageCode: tg.language_code ?? null,
      isPremium: tg.is_premium ?? false,
    };
    const user = await this.db.user.upsert({
      where: { telegramId: BigInt(tg.id) },
      create: { telegramId: BigInt(tg.id), ...fields },
      update: { ...fields, lastSeenAt: new Date() },
    });

    await this.db.profile.upsert({ where: { userId: user.id }, create: { userId: user.id }, update: {} });
    await this.db.wallet.createMany({
      data: CURRENCIES.map((currency) => ({ userId: user.id, currency })),
      skipDuplicates: true,
    });
    if (this.signupBonus > 0) {
      await this.ledger.post({
        userId: user.id,
        currency: 'CREDITS',
        amount: BigInt(this.signupBonus),
        type: 'SIGNUP_BONUS',
        source: 'signup',
        idempotencyKey: `signup:${user.id}`,
      });
    }
    return user;
  }

  async findById(id: string): Promise<User | null> {
    return this.db.user.findUnique({ where: { id } });
  }

  async wallet(userId: string): Promise<WalletDto> {
    const rows = await this.db.wallet.findMany({ where: { userId } });
    const get = (c: Currency) => toNumber(rows.find((r) => r.currency === c)?.balance ?? 0n);
    return { credits: get('CREDITS'), coins: get('COINS'), diamonds: get('DIAMONDS') };
  }

  async me(userId: string): Promise<MeDto | null> {
    const user = await this.db.user.findUnique({ where: { id: userId }, include: { profile: true } });
    if (!user?.profile) return null;
    const [wallet, unlocked, total, lastDaily] = await Promise.all([
      this.wallet(userId),
      this.db.userAchievement.count({ where: { userId, unlockedAt: { not: null } } }),
      this.db.achievement.count(),
      this.lastDailyCredits(userId),
    ]);
    const profile = user.profile;
    const now = Date.now();
    const bonusReady = profile.bonusLastAt ? profile.bonusLastAt.getTime() + RATING.bonus.cooldownMs : null;
    const dailyReady = lastDaily ? lastDaily.getTime() + DAILY_CREDITS.cooldownMs : null;
    const bonusReset = profile.lastPlayedAt !== null && now - profile.lastPlayedAt.getTime() > RATING.bonus.resetAfterMs;
    return {
      ...publicUser(user, profile),
      firstName: user.firstName,
      lastName: user.lastName,
      languageCode: user.languageCode,
      wallet,
      stats: stats(profile, unlocked, total),
      premiumUntil: profile.premiumUntil?.toISOString() ?? null,
      bonus: {
        multiplier: bonusReset ? RATING.bonus.min : profile.bonusMultiplier,
        availableAt: bonusReady && bonusReady > now ? new Date(bonusReady).toISOString() : null,
        streak: bonusReset ? 0 : profile.bonusStreak,
      },
      dailyCredits: {
        available: wallet.credits < DAILY_CREDITS.belowBalance && (!dailyReady || dailyReady <= now),
        availableAt: dailyReady && dailyReady > now ? new Date(dailyReady).toISOString() : null,
      },
    };
  }

  async lastDailyCredits(userId: string): Promise<Date | null> {
    const row = await this.db.transaction.findFirst({
      where: { userId, type: 'DAILY_BONUS' },
      orderBy: { createdAt: 'desc' },
      select: { createdAt: true },
    });
    return row?.createdAt ?? null;
  }

  async publicProfile(userId: string): Promise<PublicUserDto | null> {
    const user = await this.db.user.findUnique({ where: { id: userId }, include: { profile: true } });
    return user?.profile ? publicUser(user, user.profile) : null;
  }
}

export function publicUser(user: User, profile: Profile): PublicUserDto {
  return {
    id: user.id,
    name: displayName(user),
    username: user.username,
    photoUrl: user.photoUrl,
    rating: profile.rating,
  };
}

function stats(profile: Profile, unlocked: number, total: number): MeDto['stats'] {
  const decided = profile.gamesWon + profile.gamesLost;
  return {
    rating: profile.rating,
    totalWinnings: toNumber(profile.totalWinnings),
    gamesPlayed: profile.gamesPlayed,
    gamesWon: profile.gamesWon,
    gamesLost: profile.gamesLost,
    winRate: decided ? Math.round((profile.gamesWon / decided) * 100) : 0,
    winStreak: profile.winStreak,
    bestStreak: profile.bestStreak,
    achievementsUnlocked: unlocked,
    achievementsTotal: total,
  };
}
