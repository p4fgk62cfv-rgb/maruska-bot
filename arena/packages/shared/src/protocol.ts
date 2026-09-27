import type { z } from 'zod';
import type { GameEvent, PlayerView } from '@arena/game-engine';
import type { clientMessageSchema } from './schemas.js';
import type { AppErrorCode } from './errors.js';
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
  level: number;
  connected: boolean;
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
  | { type: 'GAME_STATE'; state: PlayerView; players: PlayerInfo[] }
  /** Engine events for animations. Already filtered: no hidden cards inside. */
  | { type: 'GAME_EVENTS'; gameId: string; version: number; events: GameEvent[] }
  | { type: 'GAME_FINISHED'; gameId: string; result: GameResultDto }
  | { type: 'PLAYER_CONNECTED'; roomId: string; userId: string }
  | { type: 'PLAYER_DISCONNECTED'; roomId: string; userId: string; graceUntil: number }
  | { type: 'PLAYER_RECONNECTED'; roomId: string; userId: string };

export interface GameResultDto {
  kind: 'loser' | 'draw';
  loserId: string | null;
  winnerId: string | null;
  payouts: { userId: string; net: number; place: number | null }[];
  stake: number;
}

export const WS_CLOSE = {
  UNAUTHORIZED: 4001,
  REPLACED: 4002,
  SERVER_SHUTDOWN: 4003,
} as const;
