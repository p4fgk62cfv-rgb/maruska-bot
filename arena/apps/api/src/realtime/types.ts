import type { GameState } from '@arena/game-engine';
import type { RoomSettings, RoomStatus } from '@arena/shared';

export interface Seat {
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
  /** Tournament match rooms: pre-seated, no stake, leaving or not showing up loses the match. */
  tournament?: { id: string; title: string; round: number; matchId: string } | null;
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
  /** Reconnect reserve left per player (ms); missing means the full reserve. */
  reserve?: Record<string, number>;
  /** The player whose turn ran out while offline and is being waited for. */
  grace?: { userId: string; since: number } | null;
}
