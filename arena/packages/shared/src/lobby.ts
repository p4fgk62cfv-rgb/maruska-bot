import type { z } from 'zod';
import type { roomFilterSchema, roomSettingsSchema } from './schemas.js';

/** Stakes on a 1–2.5–5 ladder: the stake slider snaps to these. */
export const STAKE_OPTIONS = [
  100, 250, 500, 1_000, 2_500, 5_000, 10_000, 25_000, 50_000, 100_000, 250_000, 500_000, 1_000_000, 2_500_000, 5_000_000, 10_000_000,
] as const;

/** The four pairs a room is set up with; the lobby filter accepts either side of each pair. */
export const MODE_PAIRS = [
  ['podkidnoy', 'perevodnoy'],
  ['neighbors', 'all'],
  ['cheaters', 'fair'],
  ['classic', 'draw'],
] as const;
export type GameMode = (typeof MODE_PAIRS)[number][number];

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
  frame: string | null;
  crown: string | null;
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
  /** Set for tournament matches: no stake, no leaving without losing the match. */
  tournament: { id: string; title: string; round: number } | null;
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

/**
 * Lobby filter: every non-empty group must match; empty groups mean "any".
 * Modes are matched per pair: ticking «Подкидной» and «Переводной» accepts both.
 */
export function matchesFilter(room: FilterableRoom, filter: RoomFilter): boolean {
  const s = room.settings;
  if (filter.stakes.length && !filter.stakes.includes(s.stake)) return false;
  if (filter.stakeMin !== undefined && s.stake < filter.stakeMin) return false;
  if (filter.stakeMax !== undefined && s.stake > filter.stakeMax) return false;
  if (filter.players.length && !filter.players.includes(s.players)) return false;
  if (filter.deckSizes.length && !filter.deckSizes.includes(s.deckSize)) return false;
  if (filter.speeds.length && !filter.speeds.includes(s.speed)) return false;
  if (filter.server && filter.server !== room.server) return false;
  const values: readonly string[] = [s.variant, s.throwIn, s.fairness, s.ending];
  for (const pair of MODE_PAIRS) {
    const wanted = filter.modes.filter((m) => (pair as readonly string[]).includes(m));
    if (wanted.length && !wanted.some((m) => values.includes(m))) return false;
  }
  return true;
}

export const EMPTY_FILTER: RoomFilter = { scope: 'open', stakes: [], players: [], deckSizes: [], speeds: [], modes: [] };

export const EMOJIS = [
  '😀', '😂', '🤣', '😊', '😉', '😎',
  '😍', '🥰', '😘', '😚', '💋', '❤️',
  '💕', '💖', '💔', '🌹', '🤗', '😇',
  '😏', '😜', '🤪', '🤔', '🙄', '😴',
  '😱', '😳', '🥺', '😭', '😡', '🤬',
  '👍', '👎', '👏', '🙏', '🤝', '👋',
  '💪', '🔥', '💯', '🥳', '🎉', '🍀',
  '🃏', '🤡', '💀', '💩', '🍺', '☕',
] as const;

/**
 * Smile packs are shop items (kind EMOJI). The classic pack is the emoji above and is free;
 * a picture pack is a set of stickers «pack:NN» drawn from /emoji/<pack>/NN.webp.
 */
export const EMOJI_PACKS = {
  emoji_pack_basic: { title: 'Классические смайлы', stickers: null },
  emoji_pack_panda: { title: 'Смайлы «Панда»', stickers: { prefix: 'panda', count: 25 } },
  emoji_pack_santa: { title: 'Смайлы «Новогодняя панда»', stickers: { prefix: 'santa', count: 25 } },
  emoji_pack_smile: { title: 'Смайлы «Колобок»', stickers: { prefix: 'smile', count: 25 } },
  emoji_pack_horse: { title: 'Смайлы «Лошадка»', stickers: { prefix: 'horse', count: 25 } },
  emoji_pack_cat: { title: 'Смайлы «Котик»', stickers: { prefix: 'cat', count: 25 } },
  emoji_pack_raccoon: { title: 'Смайлы «Енот»', stickers: { prefix: 'raccoon', count: 25 } },
} as const;
export type EmojiPackKey = keyof typeof EMOJI_PACKS;
export const DEFAULT_EMOJI_PACK: EmojiPackKey = 'emoji_pack_basic';

function stickerIds(prefix: string, count: number): string[] {
  return Array.from({ length: count }, (_, i) => `${prefix}:${String(i + 1).padStart(2, '0')}`);
}
export const STICKERS = Object.values(EMOJI_PACKS).flatMap((p) => (p.stickers ? stickerIds(p.stickers.prefix, p.stickers.count) : []));

/** Everything a player may send: a classic emoji or a sticker from a pack. */
export const SMILES = [...EMOJIS, ...STICKERS] as [string, ...string[]];
export type Emoji = string;

/** The smiles a pack offers, in picker order. */
export function smilesOf(pack: string): string[] {
  const def = EMOJI_PACKS[pack as EmojiPackKey] ?? EMOJI_PACKS[DEFAULT_EMOJI_PACK];
  return def.stickers ? stickerIds(def.stickers.prefix, def.stickers.count) : [...EMOJIS];
}

/** The pack a sticker belongs to, or null for a classic emoji (free for everyone). */
export function packOfSmile(smile: string): EmojiPackKey | null {
  const prefix = smile.includes(':') ? smile.split(':')[0] : null;
  if (!prefix) return null;
  for (const [key, def] of Object.entries(EMOJI_PACKS)) if (def.stickers?.prefix === prefix) return key as EmojiPackKey;
  return null;
}

/** Picture of a sticker, or null for a classic emoji. */
export function stickerUrl(smile: string): string | null {
  const [prefix, n] = smile.split(':');
  return n ? `/emoji/${prefix}/${n}.webp` : null;
}
