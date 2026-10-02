/** REST DTOs shared by apps/api and apps/web. Money is sent as number (all balances stay below 2^53). */

export type Currency = 'CREDITS' | 'COINS' | 'DIAMONDS';

export interface WalletDto {
  credits: number;
  coins: number;
  diamonds: number;
}

export interface ProfileStatsDto {
  /** League, level, stars and bars are derived on the client with ratingBadge(rating). */
  rating: number;
  totalWinnings: number;
  gamesPlayed: number;
  gamesWon: number;
  gamesLost: number;
  winRate: number;
  winStreak: number;
  bestStreak: number;
  achievementsUnlocked: number;
  achievementsTotal: number;
}

export interface BonusDto {
  multiplier: number;
  /** null — the bonus is ready for the next win. */
  availableAt: string | null;
  streak: number;
}

export interface PublicUserDto {
  id: string;
  name: string;
  username: string | null;
  photoUrl: string | null;
  rating: number;
}

export interface MeDto extends PublicUserDto {
  firstName: string;
  lastName: string | null;
  languageCode: string | null;
  /** Name set in «Настройки»; `name` already shows it. */
  nickname: string | null;
  telegramName: string;
  /** An uploaded picture replaces the Telegram photo. */
  customAvatar: boolean;
  wallet: WalletDto;
  stats: ProfileStatsDto;
  premiumUntil: string | null;
  equipped: EquippedDto;
  bonus: BonusDto;
  dailyCredits: { available: boolean; availableAt: string | null };
  /** Game owner (OWNER_IDS): sees «Управление» — the announcement and gifts. */
  owner: boolean;
}

export type LeaderboardBy = 'rating' | 'winnings' | 'wins';

export interface LeaderboardRowDto extends PublicUserDto {
  place: number;
  totalWinnings: number;
  gamesWon: number;
}

export interface SeasonDto {
  id: string;
  title: string;
  startsAt: string;
  endsAt: string;
  top: (PublicUserDto & { place: number; seasonRating: number })[];
  me: { place: number | null; seasonRating: number };
}

/** Cosmetics a player has on, by item key. Card back and table are personal; frame and crown are seen by others. */
export interface EquippedDto {
  cardBack: string;
  table: string;
  frame: string | null;
  crown: string | null;
  effect: string | null;
  /** Smile pack shown in the picker (see EMOJI_PACKS). */
  emoji: string;
}

export const DEFAULT_EQUIPPED: EquippedDto = { cardBack: 'back_classic', table: 'table_felt', frame: null, crown: null, effect: null, emoji: 'emoji_pack_basic' };

export interface AuthResponse {
  token: string;
  expiresAt: number;
  me: MeDto;
  /** start_param from the Telegram link, e.g. "game_AB12CD34", already verified by the server. */
  startParam: string | null;
}

export interface TransactionDto {
  id: string;
  currency: Currency;
  amount: number;
  type: string;
  source: string;
  balanceBefore: number;
  balanceAfter: number;
  createdAt: string;
}

export interface ServerDto {
  key: string;
  name: string;
  color: string;
  ratingBonus: number;
  online: number;
}

export interface AchievementDto {
  key: string;
  title: string;
  description: string;
  icon: string;
  goal: number;
  progress: number;
  unlockedAt: string | null;
}

export type ItemKind = 'CARD_BACK' | 'AVATAR' | 'FRAME' | 'TABLE' | 'EFFECT' | 'EMOJI' | 'CROWN';

export interface ItemDto {
  key: string;
  kind: ItemKind;
  name: string;
  rarity: 'COMMON' | 'RARE' | 'EPIC' | 'LEGENDARY';
  price: number;
  currency: Currency;
  owned: boolean;
  equipped: boolean;
}

export type Presence = 'online' | 'in_game' | 'offline';

export interface FriendDto extends PublicUserDto {
  presence: Presence;
  /** When they were last in the game (ISO); shown as «был(а) в 20:41» while offline. */
  lastSeenAt: string;
  /** «Избранное» — shown first. */
  favorite: boolean;
  /** I asked to be told when they finish their game. */
  watching: boolean;
}

/** A player in «Избранные» (not necessarily a friend). */
export interface FavoriteDto extends FriendDto {
  relation: Relation;
}

export interface FriendRequestDto {
  id: string;
  user: PublicUserDto;
  createdAt: string;
}

export interface FriendRequestsDto {
  incoming: FriendRequestDto[];
  outgoing: FriendRequestDto[];
}

/** Relation of the viewer to another player, shown on buttons («Добавить», «Заявка отправлена»…). */
export type Relation = 'self' | 'friend' | 'outgoing' | 'incoming' | 'none';

export interface RecentPlayerDto extends PublicUserDto {
  relation: Relation;
  lastPlayedAt: string;
  games: number;
}

export interface SearchUserDto extends PublicUserDto {
  relation: Relation;
}

export interface SendRequestResult {
  /** 'friends' when the other side had already asked — the request is accepted at once. */
  status: 'sent' | 'friends' | 'already_friends' | 'already_sent';
}

export type TournamentStatus = 'ANNOUNCED' | 'REGISTRATION' | 'RUNNING' | 'FINISHED' | 'CANCELLED';

export interface TournamentDto {
  id: string;
  title: string;
  status: TournamentStatus;
  prizePool: number;
  entryFee: number;
  currency: Currency;
  players: number;
  maxPlayers: number;
  startsAt: string;
  /** The viewer is registered. */
  joined: boolean;
  /** Game rules of the matches, e.g. ['Подкидной', 'Все', 'Классика']. */
  modes: string[];
}

export interface TournamentMatchDto {
  id: string;
  round: number;
  slot: number;
  a: PublicUserDto;
  b: PublicUserDto | null;
  winnerId: string | null;
  status: 'PENDING' | 'PLAYING' | 'DONE';
  decidedBy: string | null;
}

export interface TournamentDetailDto extends TournamentDto {
  rounds: number;
  prizes: number[];
  entrants: (PublicUserDto & { place: number | null; prize: number | null; eliminatedRound: number | null })[];
  matches: TournamentMatchDto[];
}

/** Opponent card opened from the table: season and all-time numbers, badges, my private label. */
export interface PlayerCardDto extends PublicUserDto {
  frame: string | null;
  crown: string | null;
  premium: boolean;
  season: { title: string; rating: number; winnings: number; wins: number } | null;
  total: { rating: number; winnings: number; wins: number; games: number; winRate: number };
  /** Unlocked achievements, newest first. */
  achievements: { key: string; title: string; icon: string }[];
  relation: Relation;
  /** «+добавить метку» — only the viewer ever sees it. */
  note: string | null;
  bot?: boolean;
}

export type MatchOutcome = 'win' | 'loss' | 'draw' | 'left';

/** One finished game in a player's history. */
export interface MatchDto {
  gameId: string;
  /** ISO time the game ended. */
  at: string;
  stake: number;
  outcome: MatchOutcome;
  /** Place among those who got rid of their cards (1 = first out). */
  place: number | null;
  net: number;
  ratingGain: number;
  durationMs: number | null;
  mode: { variant: string; deckSize: number; speed: string; throwIn: string; players: number };
  opponents: (PublicUserDto & { outcome: MatchOutcome })[];
}

export interface ProfileAchievementDto {
  key: string;
  title: string;
  description: string;
  icon: string;
  unlockedAt: string;
  /** Share of all players who have it, 0–100. */
  rarity: number;
  tier: 'common' | 'rare' | 'epic' | 'legendary';
}

/** The game card of a player: who they are, how they play, what they have won. */
export interface PlayerProfileDto extends PublicUserDto {
  frame: string | null;
  crown: string | null;
  premium: boolean;
  presence: Presence;
  lastSeenAt: string;
  memberSince: string;
  /** A bot opponent: no friends, favourites or messages. */
  bot: boolean;
  relation: Relation;
  favorite: boolean;
  /** The rarest achievement, worn as a title under the name. */
  title: ProfileAchievementDto | null;
  stats: {
    games: number;
    wins: number;
    losses: number;
    draws: number;
    winRate: number;
    streak: number;
    bestStreak: number;
    winnings: number;
    rating: number;
  };
  /** Kinds of game, most played first (from the last 200 games). */
  modes: { variant: string; deckSize: number; players: number; games: number; wins: number; share: number }[];
  /** Results of the last games, oldest first: «W», «L», «D». */
  form: ('W' | 'L' | 'D')[];
  recent: MatchDto[];
  achievements: ProfileAchievementDto[];
  achievementsTotal: number;
  /** Viewer vs this player; null on my own profile. */
  together: { games: number; myWins: number; theirWins: number; draws: number; recent: MatchDto[] } | null;
  season: { title: string; rating: number; wins: number } | null;
}

export type ReportReasonDto = 'cheating' | 'collusion' | 'insult' | 'other';

export const REPORT_REASON_RU: Record<ReportReasonDto, string> = {
  cheating: 'Жульничает',
  collusion: 'Играет в сговоре',
  insult: 'Оскорбительные имя или фото',
  other: 'Другое',
};

/** Pop-up on the start screen for everyone who opens the game; `id` changes with every new text. */
export interface AnnouncementDto {
  id: string;
  title: string;
  text: string;
  createdAt: string;
}

export interface OwnerPlayerDto {
  id: string;
  telegramId: string;
  name: string;
  username: string | null;
  photoUrl: string | null;
  credits: number;
  coins: number;
}

/** Gift for every newcomer, set by the owner in «Управление». */
/** Bot opponents: they fill empty seats at public tables after `delaySec` without a person. */
export interface BotSettingsDto {
  enabled: boolean;
  delaySec: number;
  level: 'easy' | 'normal' | 'hard';
}

export interface WelcomeGiftDto {
  enabled: boolean;
  credits: number;
  coins: number;
}
