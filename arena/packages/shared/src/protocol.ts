import type { z } from 'zod';
import type { GameEvent, PlayerView } from '@arena/game-engine';
import type { clientMessageSchema } from './schemas.js';
import type { AppErrorCode } from './errors.js';
import type { Presence, PublicUserDto } from './api.js';
import type { RoomDto } from './lobby.js';

/**
 * WebSocket protocol on /ws. One socket per client, authenticated with the session
 * token (query `?token=`). Every client message may carry `rid` (request id); the
 * server echoes it in the ACK/ERROR so the client can match replies and the server
 * can drop duplicates.
 */

export type ClientMessage = z.infer<typeof clientMessageSchema>;

export interface PlayerInfo {
  userId: string;
  name: string;
  photoUrl: string | null;
  rating: number;
  premium: boolean;
  frame: string | null;
  crown: string | null;
  connected: boolean;
  bot?: boolean;
}

export type ServerMessage =
  | { type: 'PONG'; rid?: string; serverTime: number }
  | { type: 'ACK'; rid: string }
  | { type: 'ERROR'; rid?: string; code: AppErrorCode; message: string }
  | { type: 'LOBBY_SNAPSHOT'; rooms: RoomDto[] }
  | { type: 'ROOM_CREATED'; room: RoomDto }
  | { type: 'ROOM_UPDATED'; room: RoomDto }
  | { type: 'ROOM_REMOVED'; roomId: string }
  | { type: 'ROOM_JOINED'; room: RoomDto; userId: string }
  | { type: 'ROOM_LEFT'; room: RoomDto; userId: string }
  | { type: 'GAME_STARTED'; roomId: string; gameId: string; players: PlayerInfo[] }
  /** Full personalised snapshot; sent on start, on reconnect and after every accepted action. */
  | {
      type: 'GAME_STATE';
      state: PlayerView;
      players: PlayerInfo[];
      features: { hints: boolean; discardReminder: boolean; canUndo: boolean };
      /** A player lost the connection on their turn: the table waits for them until `until`. */
      waiting?: { userId: string; until: number } | null;
    }
  /** Engine events for animations. Already filtered: no hidden cards inside. */
  | { type: 'GAME_EVENTS'; gameId: string; version: number; events: GameEvent[] }
  | { type: 'GAME_FINISHED'; gameId: string; result: GameResultDto }
  | { type: 'EMOJI'; gameId: string | null; roomId?: string; userId: string; emoji: string }
  | { type: 'PLAYER_CONNECTED'; roomId: string; userId: string }
  | { type: 'PLAYER_DISCONNECTED'; roomId: string; userId: string; graceUntil: number }
  | { type: 'PLAYER_RECONNECTED'; roomId: string; userId: string }
  | { type: 'FRIEND_REQUEST'; from: PublicUserDto }
  | { type: 'FRIEND_ACCEPTED'; friend: PublicUserDto }
  /** A friend came online, sat down to play, finished or left. */
  | { type: 'FRIEND_PRESENCE'; userId: string; presence: Presence }
  /** A friend I was watching has finished their game. */
  | { type: 'FRIEND_FREE'; friend: PublicUserDto; presence: Presence }
  /** A friend calls you to their table; `invite` lets you in without the password. */
  | { type: 'ROOM_INVITE'; from: PublicUserDto; room: RoomDto; invite: string }
  | { type: 'TOURNAMENT_MATCH'; tournamentId: string; title: string; round: number; roomId: string }
  /** Coins for an invite: `invitee` — I came by `friend`'s link; otherwise `friend` came by mine. */
  | { type: 'REFERRAL_REWARD'; friend: PublicUserDto; coins: number; invitee: boolean }
  /** Someone at my table asks to swap chairs with me (before the deal). */
  | { type: 'SEAT_SWAP_ASKED'; roomId: string; from: { userId: string; name: string; seat: number } }
  | { type: 'SEAT_SWAP_DECLINED'; roomId: string; by: { userId: string; name: string } };

export interface GameResultDto {
  kind: 'loser' | 'draw';
  /** Why the fool lost: last with cards, gave up, ran out of time, or threw the last card («Классика»). */
  reason: 'cards' | 'surrender' | 'timeout' | 'last_attack' | 'cancelled' | null;
  loserId: string | null;
  winnerId: string | null;
  payouts: { userId: string; net: number; place: number | null; ratingGain: number; bonusMultiplier: number }[];
  stake: number;
}

export const WS_CLOSE = {
  UNAUTHORIZED: 4001,
  REPLACED: 4002,
  SERVER_SHUTDOWN: 4003,
} as const;
