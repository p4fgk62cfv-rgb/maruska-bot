import type { MeDto, PublicUserDto, WalletDto } from '@arena/shared';
import type { Db } from '../db.js';
import type { Currency, Profile, User } from '../generated/prisma/client.js';
import { toNumber } from '../lib/money.js';
import type { TelegramUser } from '../telegram/initData.js';
import type { Ledger } from './ledger.js';
import { levelFromXp } from './progress.js';

const CURRENCIES: Currency[] = ['CHIPS', 'COINS', 'DIAMONDS'];

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
        currency: 'CHIPS',
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
    return { chips: get('CHIPS'), coins: get('COINS'), diamonds: get('DIAMONDS') };
  }

  async me(userId: string): Promise<MeDto | null> {
    const user = await this.db.user.findUnique({ where: { id: userId }, include: { profile: true } });
    if (!user?.profile) return null;
    const [wallet, unlocked, total] = await Promise.all([
      this.wallet(userId),
      this.db.userAchievement.count({ where: { userId, unlockedAt: { not: null } } }),
      this.db.achievement.count(),
    ]);
    return {
      ...publicUser(user, user.profile),
      firstName: user.firstName,
      lastName: user.lastName,
      languageCode: user.languageCode,
      wallet,
      stats: stats(user.profile, unlocked, total),
    };
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
    level: levelFromXp(profile.xp).level,
    rating: profile.rating,
  };
}

function stats(profile: Profile, unlocked: number, total: number): MeDto['stats'] {
  const progress = levelFromXp(profile.xp);
  const decided = profile.gamesWon + profile.gamesLost;
  return {
    level: progress.level,
    xp: profile.xp,
    xpToNext: progress.toNext,
    rating: profile.rating,
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
