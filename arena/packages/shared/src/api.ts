/** REST DTOs shared by apps/api and apps/web. Money is sent as number (all balances stay below 2^53). */

export type Currency = 'CHIPS' | 'COINS' | 'DIAMONDS';

export interface WalletDto {
  chips: number;
  coins: number;
  diamonds: number;
}

export interface ProfileStatsDto {
  level: number;
  xp: number;
  xpToNext: number;
  rating: number;
  gamesPlayed: number;
  gamesWon: number;
  gamesLost: number;
  winRate: number;
  winStreak: number;
  bestStreak: number;
  achievementsUnlocked: number;
  achievementsTotal: number;
}

export interface PublicUserDto {
  id: string;
  name: string;
  username: string | null;
  photoUrl: string | null;
  level: number;
  rating: number;
}

export interface MeDto extends PublicUserDto {
  firstName: string;
  lastName: string | null;
  languageCode: string | null;
  wallet: WalletDto;
  stats: ProfileStatsDto;
}

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

export interface FriendDto extends PublicUserDto {
  presence: 'online' | 'in_game' | 'offline';
}

export interface TournamentDto {
  id: string;
  title: string;
  status: 'ANNOUNCED' | 'REGISTRATION' | 'RUNNING' | 'FINISHED' | 'CANCELLED';
  prizePool: number;
  entryFee: number;
  currency: Currency;
  players: number;
  maxPlayers: number;
  startsAt: string;
}
