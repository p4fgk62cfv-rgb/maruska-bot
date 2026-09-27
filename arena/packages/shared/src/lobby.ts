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

/** Telegram deep link that opens the Mini App straight into a room. */
export function roomDeepLink(botUsername: string, appShortName: string | null, roomId: string): string {
  const startapp = `game_${roomId}`;
  return appShortName
    ? `https://t.me/${botUsername}/${appShortName}?startapp=${startapp}`
    : `https://t.me/${botUsername}?startapp=${startapp}`;
}

export function parseRoomStartParam(value: string | null | undefined): string | null {
  const match = /^game_([A-Za-z0-9]{6,16})$/.exec(value ?? '');
  return match ? match[1]! : null;
}
