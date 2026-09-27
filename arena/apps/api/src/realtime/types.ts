import type { GameState } from '@arena/game-engine';
import type { RoomSettings, RoomStatus } from '@arena/shared';

export interface Seat {
  userId: string;
  name: string;
  photoUrl: string | null;
  rating: number;
  premium: boolean;
  ready: boolean;
  connected: boolean;
}

export type RoomConfig = Omit<RoomSettings, 'password' | 'isPrivate' | 'server'>;

/** Live room. Plain data so it can be snapshotted to Redis as JSON. */
export interface Room {
  id: string;
  server: string;
  ownerId: string;
  isPrivate: boolean;
  passwordHash: string | null;
  settings: RoomConfig;
  status: RoomStatus;
  seats: Seat[];
  gameId: string | null;
  createdAt: number;
  readyDeadline: number | null;
}

export interface Features {
  hints: boolean;
  discardReminder: boolean;
}

/** Everything needed to resume a game after a restart. */
export interface GameSnapshot {
  gameId: string;
  roomId: string;
  stake: number;
  state: GameState;
  /** State before the last card move — for «вернуть карту». */
  previous: GameState | null;
  features: Record<string, Features>;
  transfers: Record<string, number>;
  startedAt: number;
}
