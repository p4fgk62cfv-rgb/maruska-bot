import type { z } from 'zod';
import type { roomFilterSchema, roomSettingsSchema } from './schemas.js';

export const STAKE_OPTIONS = [100, 1_000, 10_000, 100_000, 1_000_000, 10_000_000] as const;

export type RoomSettings = z.infer<typeof roomSettingsSchema>;
export type RoomFilter = z.infer<typeof roomFilterSchema>;

export type RoomStatus = 'waiting' | 'playing' | 'finished' | 'closed';

export interface RoomSeatDto {
  seat: number;
  userId: string;
  name: string;
  photoUrl: string | null;
  rating: number;
  premium: boolean;
  ready: boolean;
  connected: boolean;
}

export interface RoomDto {
  id: string;
  server: string;
  status: RoomStatus;
  ownerId: string;
  isPrivate: boolean;
  settings: Omit<RoomSettings, 'password' | 'isPrivate' | 'server'>;
  seats: RoomSeatDto[];
  gameId: string | null;
  createdAt: number;
  /** Someone at the table has premium: such rooms are listed first. */
  premium: boolean;
  /** When the not-ready players will be removed from a full room (epoch ms). */
  readyDeadline: number | null;
}

/** Members only: the invite link carries a code that lets friends skip the password. */
export interface RoomInviteDto {
  link: string;
  shareUrl: string;
}

export interface MyRoomDto {
  room: RoomDto;
  invite: RoomInviteDto;
}

export const MODE_LABEL_RU: Record<string, string> = {
  podkidnoy: 'Подкидной',
  perevodnoy: 'Переводной',
  all: 'Все',
  neighbors: 'Соседи',
  fair: 'Честная игра',
  cheaters: 'С шулерами',
  classic: 'Классика',
  draw: 'Ничья',
};

export const SPEED_LABEL_RU = { normal: 'Обычная', fast: 'Быстрая' } as const;

/** 50 000 → "50K", 1 000 000 → "1M" */
export function formatStake(value: number): string {
  if (value >= 1_000_000) return `${value / 1_000_000}M`;
  if (value >= 1_000) return `${value / 1_000}K`;
  return String(value);
}

/**
 * Telegram deep link that opens the Mini App straight into a room.
 * start_param allows only [A-Za-z0-9_-], up to 64 chars: game_<roomId>[_<inviteCode>].
 */
export function roomDeepLink(botUsername: string, appShortName: string | null, roomId: string, invite?: string): string {
  const startapp = invite ? `game_${roomId}_${invite}` : `game_${roomId}`;
  return appShortName
    ? `https://t.me/${botUsername}/${appShortName}?startapp=${startapp}`
    : `https://t.me/${botUsername}?startapp=${startapp}`;
}

export function parseRoomStartParam(value: string | null | undefined): { roomId: string; invite: string | null } | null {
  const match = /^game_([A-Z0-9]{8})(?:_([A-Za-z0-9-]{6,24}))?$/.exec(value ?? '');
  return match ? { roomId: match[1]!, invite: match[2] ?? null } : null;
}

type FilterableRoom = Pick<RoomDto, 'settings' | 'server'>;

/** Lobby filter: every non-empty group must match; empty groups mean "any". */
export function matchesFilter(room: FilterableRoom, filter: RoomFilter): boolean {
  const s = room.settings;
  if (filter.stakes.length && !filter.stakes.includes(s.stake)) return false;
  if (filter.players.length && !filter.players.includes(s.players)) return false;
  if (filter.deckSizes.length && !filter.deckSizes.includes(s.deckSize)) return false;
  if (filter.speeds.length && !filter.speeds.includes(s.speed)) return false;
  if (filter.server && filter.server !== room.server) return false;
  if (filter.modes.length) {
    const values = [s.variant, s.throwIn, s.fairness, s.ending] as string[];
    if (!filter.modes.every((m) => values.includes(m))) return false;
  }
  return true;
}

export const EMPTY_FILTER: RoomFilter = { stakes: [], players: [], deckSizes: [], speeds: [], modes: [] };

export const EMOJIS = ['😀', '😂', '😎', '🤔', '😡', '😭', '👍', '👏', '🔥', '🃏', '🍀', '💀'] as const;
