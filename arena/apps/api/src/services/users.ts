import { DAILY_CREDITS, RATING, type EquippedDto, type MeDto, type PublicUserDto, type WalletDto } from '@arena/shared';
import type { Db } from '../db.js';
import { Prisma, type Currency, type Profile, type User } from '../generated/prisma/client.js';
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

/** A picture uploaded in «Настройки» wins over the Telegram photo; the version busts caches. */
export function avatarUrl(user: Pick<User, 'id' | 'photoUrl'>, profile: Pick<Profile, 'avatarVersion'>): string | null {
  return profile.avatarVersion ? `/api/avatars/${user.id}?v=${profile.avatarVersion}` : user.photoUrl;
}

export class UserService {
  constructor(
    private readonly db: Db,
    private readonly ledger: Ledger,
    private readonly signupBonus: number,
    private readonly items: { equipped(userId: string): Promise<EquippedDto> },
  ) {}

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
    const user = await this.upsertUser(BigInt(tg.id), fields);

    // INSERT … ON CONFLICT DO NOTHING: two first logins at the same moment must both succeed.
    await this.db.profile.createMany({ data: [{ userId: user.id }], skipDuplicates: true });
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

  /** Upsert that survives a concurrent first login (Prisma may run it as select + insert). */
  private async upsertUser(telegramId: bigint, fields: Omit<Prisma.UserCreateInput, 'telegramId'>): Promise<User> {
    const write = () =>
      this.db.user.upsert({
        where: { telegramId },
        create: { telegramId, ...fields },
        update: { ...fields, lastSeenAt: new Date() },
      });
    try {
      return await write();
    } catch (error) {
      if (error instanceof Prisma.PrismaClientKnownRequestError && error.code === 'P2002') return write();
      throw error;
    }
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
    const [wallet, unlocked, total, lastDaily, equipped] = await Promise.all([
      this.wallet(userId),
      this.db.userAchievement.count({ where: { userId, unlockedAt: { not: null } } }),
      this.db.achievement.count(),
      this.lastDailyCredits(userId),
      this.items.equipped(userId),
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
      nickname: profile.nickname,
      telegramName: displayName(user),
      customAvatar: profile.avatarVersion !== null,
      wallet,
      stats: stats(profile, unlocked, total),
      premiumUntil: profile.premiumUntil?.toISOString() ?? null,
      equipped,
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
    name: profile.nickname || displayName(user),
    username: user.username,
    photoUrl: avatarUrl(user, profile),
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
