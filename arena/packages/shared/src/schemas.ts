/**
 * Runtime validators (zod). Imported by the server via `@arena/shared/schemas`;
 * the web bundle only needs the inferred types and stays zod-free.
 */
import { z } from 'zod';
import { isCardId, type CardId } from '@arena/game-engine';
import { SMILES, STAKE_OPTIONS } from './lobby.js';

export const roomSettingsSchema = z.object({
  stake: z.number().int().refine((v) => (STAKE_OPTIONS as readonly number[]).includes(v), 'stake'),
  players: z.number().int().min(2).max(6),
  deckSize: z.union([z.literal(24), z.literal(36), z.literal(52)]),
  speed: z.enum(['normal', 'fast']),
  variant: z.enum(['podkidnoy', 'perevodnoy']),
  throwIn: z.enum(['all', 'neighbors']),
  fairness: z.enum(['fair', 'cheaters']),
  ending: z.enum(['classic', 'draw']),
  server: z.string().min(1).max(32),
  isPrivate: z.boolean(),
  password: z.string().min(1).max(32).optional(),
  /** Empty seats are taken by bots when nobody comes. Off unless the creator ticks it. */
  bots: z.boolean().optional(),
  /** How well those bots play; the owner's default when not set. */
  botLevel: z.enum(['easy', 'normal', 'hard']).optional(),
});

/** Lobby filter: every field is a set of accepted values; an empty set means "any". */
export const joinRoomSchema = z.object({
  password: z.string().max(32).optional(),
  invite: z.string().max(24).optional(),
});

export const quickGameSchema = z.object({ stake: z.number().int().optional() });

export const roomFilterSchema = z.object({
  /** «Открытые» lists public tables, «Приватные» the password-protected ones. */
  scope: z.enum(['open', 'private']).default('open'),
  stakes: z.array(z.number().int()).default([]),
  players: z.array(z.number().int().min(2).max(6)).default([]),
  deckSizes: z.array(z.number().int()).default([]),
  speeds: z.array(z.enum(['normal', 'fast'])).default([]),
  modes: z
    .array(z.enum(['podkidnoy', 'perevodnoy', 'all', 'neighbors', 'fair', 'cheaters', 'classic', 'draw']))
    .default([]),
  server: z.string().optional(),
  stakeMin: z.number().int().nonnegative().optional(),
  stakeMax: z.number().int().nonnegative().optional(),
});

const cardSchema = z.string().refine(isCardId, 'card') as unknown as z.ZodType<CardId>;
const rid = z.string().min(1).max(64).optional();

export const clientMessageSchema = z.discriminatedUnion('type', [
  z.object({ type: z.literal('PING'), rid }),
  z.object({ type: z.literal('LOBBY_SUBSCRIBE'), rid, filter: roomFilterSchema.optional() }),
  z.object({ type: z.literal('LOBBY_UNSUBSCRIBE'), rid }),
  z.object({ type: z.literal('ROOM_WATCH'), rid, roomId: z.string() }),
  z.object({ type: z.literal('READY'), rid, roomId: z.string(), ready: z.boolean() }),
  z.object({ type: z.literal('RECONNECT'), rid, roomId: z.string(), lastVersion: z.number().int().optional() }),
  z.object({ type: z.literal('PLAY_CARD'), rid, gameId: z.string(), card: cardSchema, target: z.number().int().min(0).max(5).optional() }),
  z.object({ type: z.literal('PLAY_CARDS'), rid, gameId: z.string(), cards: z.array(cardSchema).min(1).max(6) }),
  z.object({ type: z.literal('TRANSFER'), rid, gameId: z.string(), card: cardSchema }),
  z.object({ type: z.literal('TAKE_CARDS'), rid, gameId: z.string() }),
  z.object({ type: z.literal('PASS'), rid, gameId: z.string() }),
  /** «Сдаться». */
  z.object({ type: z.literal('LEAVE_GAME'), rid, gameId: z.string() }),
  /** «С шулерами»: tap on a table card believed to be illegal. */
  z.object({ type: z.literal('REPORT_CHEAT'), rid, gameId: z.string(), seq: z.number().int().positive() }),
  /** «Вернуть карту» (coins). */
  z.object({ type: z.literal('UNDO_MOVE'), rid, gameId: z.string() }),
  /** «Подсветка» / «Напомнить отбой» (coins, until the end of the game). */
  z.object({ type: z.literal('USE_FEATURE'), rid, gameId: z.string(), feature: z.enum(['hints', 'discardReminder']) }),
  z.object({ type: z.literal('SEND_EMOJI'), rid, gameId: z.string(), emoji: z.enum(SMILES) }),
  /** A smile while the table is still gathering (or between deals). */
  z.object({ type: z.literal('ROOM_EMOJI'), rid, roomId: z.string(), emoji: z.enum(SMILES) }),
  /** Before the deal: move to a free chair, ask someone to swap, answer such a request. */
  z.object({ type: z.literal('MOVE_SEAT'), rid, roomId: z.string(), seat: z.number().int().min(0).max(5) }),
  z.object({ type: z.literal('SEAT_SWAP'), rid, roomId: z.string(), userId: z.string() }),
  z.object({ type: z.literal('SEAT_SWAP_ANSWER'), rid, roomId: z.string(), userId: z.string(), accept: z.boolean() }),
]);
