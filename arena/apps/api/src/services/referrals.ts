import { randomBytes } from 'node:crypto';
import type { GameResultDto, PublicUserDto, ReferralInfoDto, ReferralSettingsDto } from '@arena/shared';
import type { FastifyBaseLogger } from 'fastify';
import type { Config } from '../config.js';
import type { Db } from '../db.js';
import { Prisma, type User } from '../generated/prisma/client.js';
import type { Realtime } from '../realtime/realtime.js';
import type { BotService } from './bots.js';
import { publicUrl } from './friends.js';
import type { Ledger } from './ledger.js';
import type { Outbox } from './notifier.js';
import { isBanned, publicUser } from './users.js';

const KEY = 'referral';
const DEFAULTS: ReferralSettingsDto = { enabled: true, inviteeCoins: 500, referrerCoins: 500, dailyLimit: 20 };
/** Only an account this young can be attributed to an invite (the first opening of the app). */
const NEW_ACCOUNT_MS = 10 * 60_000;
const PREFIX = 'ref_';
const ALPHABET = 'abcdefghijkmnpqrstuvwxyz23456789';
const LIST = 50;

export function referralCode(): string {
  const bytes = randomBytes(8);
  return Array.from(bytes, (b) => ALPHABET[b % ALPHABET.length]).join('');
}

/** «ref_abc123» → «abc123»; anything else → null. */
export function parseReferralParam(param: string | null | undefined): string | null {
  if (!param?.startsWith(PREFIX)) return null;
  const code = param.slice(PREFIX.length);
  return /^[a-z0-9]{4,16}$/.test(code) ? code : null;
}

/**
 * «Пригласить друга»: every player has a link with a code. A newcomer who opens the app by it is
 * tied to the inviter (and they become friends); when the newcomer finishes a first game with
 * other people, both get coins. Bots do not count, the owner sets the amounts and a daily limit.
 */
export class ReferralService {
  private cached: { at: number; value: ReferralSettingsDto } | null = null;

  constructor(
    private readonly deps: {
      db: Db;
      ledger: Ledger;
      config: Config;
      bots: BotService;
      outbox: Outbox;
      realtime: Realtime;
      log: FastifyBaseLogger;
    },
  ) {}

  private get db(): Db {
    return this.deps.db;
  }

  async settings(): Promise<ReferralSettingsDto> {
    if (this.cached && Date.now() - this.cached.at < 30_000) return this.cached.value;
    const row = await this.db.setting.findUnique({ where: { key: KEY } });
    const value = { ...DEFAULTS, ...((row?.value as Partial<ReferralSettingsDto> | null) ?? {}) };
    this.cached = { at: Date.now(), value };
    return value;
  }

  async setSettings(value: ReferralSettingsDto): Promise<ReferralSettingsDto> {
    await this.db.setting.upsert({ where: { key: KEY }, create: { key: KEY, value: { ...value } }, update: { value: { ...value } } });
    this.cached = { at: Date.now(), value };
    return value;
  }

  /** The player's code, created on first use. */
  async codeOf(userId: string): Promise<string> {
    const user = await this.db.user.findUniqueOrThrow({ where: { id: userId }, select: { refCode: true } });
    if (user.refCode) return user.refCode;
    for (let attempt = 0; ; attempt++) {
      try {
        // Only set when still empty: two parallel calls end with the same code.
        await this.db.user.updateMany({ where: { id: userId, refCode: null }, data: { refCode: referralCode() } });
        return (await this.db.user.findUniqueOrThrow({ where: { id: userId }, select: { refCode: true } })).refCode!;
      } catch (error) {
        if (attempt < 3 && error instanceof Prisma.PrismaClientKnownRequestError && error.code === 'P2002') continue;
        throw error;
      }
    }
  }

  link(code: string): string | null {
    const { BOT_USERNAME, MINI_APP_SHORT_NAME } = this.deps.config;
    if (!BOT_USERNAME) return null;
    return MINI_APP_SHORT_NAME
      ? `https://t.me/${BOT_USERNAME}/${MINI_APP_SHORT_NAME}?startapp=${PREFIX}${code}`
      : `https://t.me/${BOT_USERNAME}?startapp=${PREFIX}${code}`;
  }

  /**
   * Login with a start parameter. Ties a brand-new account to the inviter: not oneself, not a
   * bot, not a player who already played or already came by someone's invite.
   */
  async attach(user: User, startParam: string | null): Promise<void> {
    const code = parseReferralParam(startParam);
    if (!code || user.isBot) return;
    if (Date.now() - user.createdAt.getTime() > NEW_ACCOUNT_MS) return;
    if (!(await this.settings()).enabled) return;
    const referrer = await this.db.user.findUnique({ where: { refCode: code } });
    if (!referrer || referrer.id === user.id || referrer.isBot || isBanned(referrer)) return;
    const played = await this.db.gamePlayer.count({ where: { userId: user.id } });
    if (played > 0) return;
    const created = await this.db.referral.createMany({ data: [{ inviteeId: user.id, referrerId: referrer.id }], skipDuplicates: true });
    if (created.count === 0) return;
    await this.db.friend.createMany({
      data: [
        { userId: referrer.id, friendId: user.id },
        { userId: user.id, friendId: referrer.id },
      ],
      skipDuplicates: true,
    });
    const newcomer = await this.publicOf(user.id);
    if (newcomer) this.deps.realtime.hub.send(referrer.id, { type: 'FRIEND_ACCEPTED', friend: newcomer });
    this.deps.log.info({ inviteeId: user.id, referrerId: referrer.id }, 'referral attached');
  }

  /** A game was settled: newcomers who just played with other people get their invite reward. */
  async onGame(result: GameResultDto): Promise<void> {
    if (result.reason === 'cancelled') return;
    const people = result.payouts.map((p) => p.userId).filter((id) => !this.deps.bots.isBot(id));
    if (people.length < 2) return;
    const pending = await this.db.referral.findMany({ where: { inviteeId: { in: people }, rewardedAt: null } });
    if (!pending.length) return;
    const settings = await this.settings();
    if (!settings.enabled) return;
    for (const ref of pending) await this.reward(ref.inviteeId, ref.referrerId, settings);
  }

  private async reward(inviteeId: string, referrerId: string, settings: ReferralSettingsDto): Promise<void> {
    const since = new Date(Date.now() - 24 * 3600_000);
    const today = await this.db.referral.count({ where: { referrerId, rewardedAt: { gte: since }, referrerCoins: { gt: 0 } } });
    const inviteeCoins = settings.inviteeCoins;
    // Past the daily limit the newcomer is still welcomed; the inviter gets nothing for this one.
    const referrerCoins = today < settings.dailyLimit ? settings.referrerCoins : 0;
    const paid = await this.db.$transaction(async (tx) => {
      const claimed = await tx.referral.updateMany({
        where: { inviteeId, rewardedAt: null },
        data: { rewardedAt: new Date(), inviteeCoins, referrerCoins },
      });
      if (claimed.count === 0) return false;
      const meta = { inviteeId, referrerId };
      if (inviteeCoins > 0) {
        await this.deps.ledger.postIn(tx, { userId: inviteeId, currency: 'COINS', amount: BigInt(inviteeCoins), type: 'REFERRAL', source: `referral:${inviteeId}`, idempotencyKey: `ref:${inviteeId}:in`, meta });
      }
      if (referrerCoins > 0) {
        await this.deps.ledger.postIn(tx, { userId: referrerId, currency: 'COINS', amount: BigInt(referrerCoins), type: 'REFERRAL', source: `referral:${inviteeId}`, idempotencyKey: `ref:${inviteeId}:ref`, meta });
      }
      return true;
    });
    if (!paid) return;
    this.deps.log.info({ inviteeId, referrerId, inviteeCoins, referrerCoins }, 'referral rewarded');
    const [invitee, referrer] = await Promise.all([this.publicOf(inviteeId), this.publicOf(referrerId)]);
    const hub = this.deps.realtime.hub;
    if (referrer && inviteeCoins > 0) hub.send(inviteeId, { type: 'REFERRAL_REWARD', friend: referrer, coins: inviteeCoins, invitee: true });
    if (invitee && referrerCoins > 0) {
      hub.send(referrerId, { type: 'REFERRAL_REWARD', friend: invitee, coins: referrerCoins, invitee: false });
      if (!hub.isOnline(referrerId)) {
        const base = publicUrl(this.deps.config);
        await this.deps.outbox
          .enqueue(referrerId, 'referral_reward', {
            text: `🎁 <b>${escapeHtml(invitee.name)}</b> сыграл(а) первую партию по вашему приглашению — вам <b>${referrerCoins}</b> монет!`,
            ...(base ? { button: { text: '🎮 Открыть Арену', webApp: `${base}/` } } : {}),
          })
          .catch((error: unknown) => this.deps.log.warn({ err: error }, 'referral notification failed'));
      }
    }
  }

  async info(userId: string): Promise<ReferralInfoDto> {
    const [settings, code] = await Promise.all([this.settings(), this.codeOf(userId)]);
    const [rows, totals, mine] = await Promise.all([
      this.db.referral.findMany({
        where: { referrerId: userId },
        orderBy: { createdAt: 'desc' },
        take: LIST,
        include: { invitee: { include: { profile: true } } },
      }),
      this.db.referral.aggregate({ where: { referrerId: userId }, _count: { _all: true }, _sum: { referrerCoins: true } }),
      this.db.referral.findUnique({ where: { inviteeId: userId }, include: { referrer: { include: { profile: true } } } }),
    ]);
    const rewarded = await this.db.referral.count({ where: { referrerId: userId, rewardedAt: { not: null } } });
    return {
      enabled: settings.enabled,
      link: this.link(code),
      inviteeCoins: settings.inviteeCoins,
      referrerCoins: settings.referrerCoins,
      invited: totals._count._all,
      rewarded,
      earned: totals._sum.referrerCoins ?? 0,
      friends: rows
        .filter((r) => r.invitee.profile)
        .map((r) => ({
          ...publicUser(r.invitee, r.invitee.profile!),
          joinedAt: r.createdAt.toISOString(),
          rewardedAt: r.rewardedAt?.toISOString() ?? null,
          coins: r.referrerCoins,
        })),
      invitedBy:
        mine && mine.referrer.profile
          ? { ...publicUser(mine.referrer, mine.referrer.profile), pending: mine.rewardedAt === null, coins: mine.rewardedAt ? mine.inviteeCoins : settings.inviteeCoins }
          : null,
    };
  }

  private async publicOf(userId: string): Promise<PublicUserDto | null> {
    const user = await this.db.user.findUnique({ where: { id: userId }, include: { profile: true } });
    return user?.profile ? publicUser(user, user.profile) : null;
  }
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
