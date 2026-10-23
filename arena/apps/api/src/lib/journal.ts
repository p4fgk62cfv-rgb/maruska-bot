import type { FastifyBaseLogger } from 'fastify';
import type { Db } from '../db.js';
import type { Prisma } from '../generated/prisma/client.js';

/** What the owner's journal records besides the moves themselves. */
export type JournalKind =
  /** A player at a running table lost / got back the connection. */
  | 'offline'
  | 'online'
  /** The turn waited for a player without connection (their reconnect reserve). */
  | 'wait'
  /** The server refused a card move (code: why). */
  | 'move_refused'
  /** A tournament table was dealt (miniId, round). */
  | 'tournament_table'
  /** A game was cancelled and the stakes refunded (why). */
  | 'cancelled'
  /** Settling a finished game failed (retried). */
  | 'settlement_failed'
  /** A mini-tournament: message to the group not delivered, players did not come, a player left, a table replayed. */
  | 'message_lost'
  | 'no_show'
  | 'forfeit'
  | 'replay';

export interface JournalEvent {
  kind: JournalKind;
  gameId?: string | null;
  roomId?: string | null;
  miniId?: string | null;
  userId?: string | null;
  details?: Record<string, unknown>;
}

const FLUSH_MS = 1_000;
const KEEP_DAYS = 30;

/**
 * The owner's journal. Recording never waits for the database and never breaks a game:
 * events are buffered and written once a second; a failed write is logged and dropped.
 */
export class Journal {
  private db: Db | null = null;
  private log: FastifyBaseLogger | null = null;
  private buffer: Prisma.GameEventCreateManyInput[] = [];
  private timer: NodeJS.Timeout | null = null;
  private cleaner: NodeJS.Timeout | null = null;

  attach(db: Db, log: FastifyBaseLogger): void {
    this.db = db;
    this.log = log;
    // Old events go once a day: the journal is for «what happened lately».
    const clean = () => void this.cleanup();
    clean();
    this.cleaner = setInterval(clean, 24 * 3600_000);
    this.cleaner.unref();
  }

  record(event: JournalEvent): void {
    if (!this.db) return;
    this.buffer.push({
      kind: event.kind,
      gameId: event.gameId ?? null,
      roomId: event.roomId ?? null,
      miniId: event.miniId ?? null,
      userId: event.userId ?? null,
      ...(event.details ? { details: event.details as Prisma.InputJsonValue } : {}),
    });
    if (!this.timer) {
      this.timer = setTimeout(() => void this.flush(), FLUSH_MS);
      this.timer.unref();
    }
  }

  async flush(): Promise<void> {
    this.timer = null;
    const batch = this.buffer.splice(0);
    if (!batch.length || !this.db) return;
    await this.db.gameEvent.createMany({ data: batch }).catch((err: unknown) => this.log?.warn({ err, count: batch.length }, 'journal write failed'));
  }

  async stop(): Promise<void> {
    if (this.timer) clearTimeout(this.timer);
    if (this.cleaner) clearInterval(this.cleaner);
    await this.flush();
    this.db = null;
  }

  private async cleanup(): Promise<void> {
    await this.db?.gameEvent
      .deleteMany({ where: { createdAt: { lt: new Date(Date.now() - KEEP_DAYS * 86_400_000) } } })
      .catch((err: unknown) => this.log?.warn({ err }, 'journal cleanup failed'));
  }
}

export const journal = new Journal();
