import type { MatchDto, MatchOutcome, PlayerProfileDto, ProfileAchievementDto, PublicUserDto } from '@arena/shared';
import { isPremium } from '@arena/shared';
import type { Db } from '../db.js';
import type { GameOutcome, Prisma } from '../generated/prisma/client.js';
import { AppError } from '../lib/errors.js';
import { toNumber } from '../lib/money.js';
import type { FriendService } from './friends.js';
import type { ItemService } from './items.js';
import type { Presence } from './presence.js';
import { isBanned, publicUser } from './users.js';

const RECENT = 10;
/** Games looked at for «Любимый тип игры». */
const MODE_SAMPLE = 200;
/** Games looked at for «Совместные партии». */
const TOGETHER_SAMPLE = 500;
const RARITY_TTL_MS = 5 * 60_000;

const OUTCOME: Record<GameOutcome, MatchOutcome> = { WIN: 'win', LOSS: 'loss', DRAW: 'draw', LEFT: 'left' };

/** Share of players who have an achievement → how it is shown. */
export function tierOf(rarity: number): ProfileAchievementDto['tier'] {
  if (rarity <= 1) return 'legendary';
  if (rarity <= 5) return 'epic';
  if (rarity <= 15) return 'rare';
  return 'common';
}

const matchInclude = {
  game: {
    select: {
      id: true,
      stake: true,
      settings: true,
      startedAt: true,
      finishedAt: true,
      result: { select: { durationMs: true } },
      players: { select: { userId: true, outcome: true, user: { include: { profile: true } } } },
    },
  },
} satisfies Prisma.GamePlayerInclude;

type MatchRow = Prisma.GamePlayerGetPayload<{ include: typeof matchInclude }>;

/** The player card: stats, favourite kind of game, last matches, rare achievements, games together. */
export class ProfileService {
  private rarity: { at: number; byId: Map<string, number> } | null = null;

  constructor(
    private readonly deps: { db: Db; items: ItemService; presence: Presence; friends: () => FriendService },
  ) {}

  private get db(): Db {
    return this.deps.db;
  }

  async profile(viewer: string, userId: string): Promise<PlayerProfileDto> {
    const now = new Date();
    const user = await this.db.user.findUnique({ where: { id: userId }, include: { profile: true } });
    const p = user?.profile;
    if (!user || !p || (isBanned(user) && viewer !== userId)) throw new AppError('NOT_FOUND');
    const friends = this.deps.friends();
    const [equipped, presence, relations, favorite, season, recent, modes, achievements, together] = await Promise.all([
      this.deps.items.equipped(userId),
      this.deps.presence.lookup([userId]),
      friends.relations(viewer, [userId]),
      viewer === userId ? Promise.resolve(false) : friends.isFavorite(viewer, userId),
      this.db.season.findFirst({ where: { startsAt: { lte: now }, endsAt: { gt: now } }, include: { ratings: { where: { userId } } } }),
      this.matches(userId, RECENT),
      this.modes(userId),
      this.achievements(userId),
      viewer === userId ? Promise.resolve(null) : this.together(viewer, userId),
    ]);
    const decided = p.gamesWon + p.gamesLost;
    const rare = achievements.filter((a) => a.tier !== 'common');
    return {
      ...publicUser(user, p),
      frame: equipped.frame,
      crown: equipped.crown,
      premium: isPremium(p.premiumUntil?.getTime() ?? null, now.getTime()),
      presence: viewer === userId ? 'online' : (presence[userId] ?? 'offline'),
      lastSeenAt: user.lastSeenAt.toISOString(),
      memberSince: user.createdAt.toISOString(),
      bot: user.isBot,
      relation: relations[userId] ?? 'none',
      favorite,
      title: rare.length ? rare.reduce((best, a) => (a.rarity < best.rarity ? a : best)) : null,
      stats: {
        games: p.gamesPlayed,
        wins: p.gamesWon,
        losses: p.gamesLost,
        draws: p.gamesDraw,
        winRate: decided ? Math.round((p.gamesWon / decided) * 100) : 0,
        streak: p.winStreak,
        bestStreak: p.bestStreak,
        winnings: toNumber(p.totalWinnings),
        rating: p.rating,
      },
      modes,
      form: recent
        .slice()
        .reverse()
        .map((m) => (m.outcome === 'win' ? 'W' : m.outcome === 'draw' ? 'D' : 'L')),
      recent,
      achievements,
      achievementsTotal: await this.db.achievement.count(),
      together,
      season: season ? { title: season.title, rating: season.ratings[0]?.rating ?? 0, wins: season.ratings[0]?.wins ?? 0 } : null,
    };
  }

  /** Finished games of a player, newest first. */
  async matches(userId: string, limit: number, before?: Date): Promise<MatchDto[]> {
    const rows = await this.db.gamePlayer.findMany({
      where: { userId, game: { status: 'FINISHED', ...(before ? { finishedAt: { lt: before } } : {}) } },
      orderBy: { game: { finishedAt: 'desc' } },
      take: limit,
      include: matchInclude,
    });
    return rows.map((row) => toMatch(row, userId));
  }

  private async modes(userId: string): Promise<PlayerProfileDto['modes']> {
    const rows = await this.db.gamePlayer.findMany({
      where: { userId, game: { status: 'FINISHED' } },
      orderBy: { game: { finishedAt: 'desc' } },
      take: MODE_SAMPLE,
      select: { outcome: true, game: { select: { settings: true, _count: { select: { players: true } } } } },
    });
    const groups = new Map<string, PlayerProfileDto['modes'][number]>();
    for (const row of rows) {
      const s = settingsOf(row.game.settings);
      const key = `${s.variant}:${s.deckSize}:${row.game._count.players}`;
      const g = groups.get(key) ?? { variant: s.variant, deckSize: s.deckSize, players: row.game._count.players, games: 0, wins: 0, share: 0 };
      g.games++;
      if (row.outcome === 'WIN') g.wins++;
      groups.set(key, g);
    }
    return [...groups.values()]
      .map((g) => ({ ...g, share: Math.round((g.games / rows.length) * 100) }))
      .sort((a, b) => b.games - a.games)
      .slice(0, 4);
  }

  private async rarities(): Promise<Map<string, number>> {
    if (this.rarity && Date.now() - this.rarity.at < RARITY_TTL_MS) return this.rarity.byId;
    const [counts, players] = await Promise.all([
      this.db.userAchievement.groupBy({ by: ['achievementId'], where: { unlockedAt: { not: null } }, _count: { _all: true } }),
      this.db.profile.count({ where: { gamesPlayed: { gt: 0 } } }),
    ]);
    const total = Math.max(1, players);
    const byId = new Map(counts.map((c) => [c.achievementId, Math.min(100, Math.round((c._count._all / total) * 1000) / 10)]));
    this.rarity = { at: Date.now(), byId };
    return byId;
  }

  /** Unlocked achievements, rarest first. */
  private async achievements(userId: string): Promise<ProfileAchievementDto[]> {
    const [rows, rarity] = await Promise.all([
      this.db.userAchievement.findMany({ where: { userId, unlockedAt: { not: null } }, include: { achievement: true } }),
      this.rarities(),
    ]);
    return rows
      .map((r) => {
        const share = rarity.get(r.achievementId) ?? 100;
        return {
          key: r.achievement.key,
          title: r.achievement.title,
          description: r.achievement.description,
          icon: r.achievement.icon,
          unlockedAt: r.unlockedAt!.toISOString(),
          rarity: share,
          tier: tierOf(share),
        };
      })
      .sort((a, b) => a.rarity - b.rarity || b.unlockedAt.localeCompare(a.unlockedAt));
  }

  /** The viewer against this player: score and the last games at one table. */
  private async together(viewer: string, userId: string): Promise<NonNullable<PlayerProfileDto['together']>> {
    const rows = await this.db.gamePlayer.findMany({
      where: { userId: viewer, game: { status: 'FINISHED', players: { some: { userId } } } },
      orderBy: { game: { finishedAt: 'desc' } },
      take: TOGETHER_SAMPLE,
      include: matchInclude,
    });
    let myWins = 0;
    let theirWins = 0;
    for (const row of rows) {
      const mine = row.outcome;
      const theirs = row.game.players.find((x) => x.userId === userId)?.outcome;
      if (mine === 'WIN' && (theirs === 'LOSS' || theirs === 'LEFT')) myWins++;
      else if (theirs === 'WIN' && (mine === 'LOSS' || mine === 'LEFT')) theirWins++;
    }
    return { games: rows.length, myWins, theirWins, draws: rows.length - myWins - theirWins, recent: rows.slice(0, RECENT).map((row) => toMatch(row, viewer)) };
  }
}

function settingsOf(raw: Prisma.JsonValue): { variant: string; deckSize: number; speed: string; throwIn: string } {
  const s = (raw ?? {}) as Record<string, unknown>;
  return {
    variant: typeof s.variant === 'string' ? s.variant : 'podkidnoy',
    deckSize: typeof s.deckSize === 'number' ? s.deckSize : 36,
    speed: typeof s.speed === 'string' ? s.speed : 'normal',
    throwIn: typeof s.throwIn === 'string' ? s.throwIn : 'all',
  };
}

function toMatch(row: MatchRow, userId: string): MatchDto {
  const g = row.game;
  const s = settingsOf(g.settings);
  return {
    gameId: g.id,
    at: (g.finishedAt ?? g.startedAt).toISOString(),
    stake: toNumber(g.stake),
    outcome: row.outcome ? OUTCOME[row.outcome] : 'draw',
    place: row.place,
    net: toNumber(row.net ?? 0n),
    ratingGain: row.ratingGain ?? 0,
    durationMs: g.result?.durationMs ?? null,
    mode: { ...s, players: g.players.length },
    opponents: g.players
      .filter((x) => x.userId !== userId && x.user.profile)
      .map((x): PublicUserDto & { outcome: MatchOutcome } => ({ ...publicUser(x.user, x.user.profile!), outcome: x.outcome ? OUTCOME[x.outcome] : 'draw' })),
  };
}
