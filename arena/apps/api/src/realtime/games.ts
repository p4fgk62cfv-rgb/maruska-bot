import { randomUUID } from 'node:crypto';
import {
  applyAction,
  applyTimeout,
  createGame,
  toPlayerView,
  undoLastMove,
  type ActionResult,
  type GameAction,
  type GameEvent,
  type GameState,
} from '@arena/game-engine';
import { errorText, FEATURE_PRICES, type AppErrorCode, type ClientMessage, type GameResultDto, type PlayerInfo } from '@arena/shared';
import type { FastifyBaseLogger } from 'fastify';
import type { Db } from '../db.js';
import type { Prisma } from '../generated/prisma/client.js';
import { AppError } from '../lib/errors.js';
import { cryptoRandom } from '../lib/ids.js';
import { metrics } from '../lib/metrics.js';
import { SerialQueue } from '../lib/serial.js';
import type { Ledger } from '../services/ledger.js';
import { NotSettleable, type SettlementService } from '../services/settlement.js';
import type { Hub } from './hub.js';
import type { SnapshotStore } from './store.js';
import type { Features, GameSnapshot, Room } from './types.js';

type GameMessage = Extract<ClientMessage, { gameId: string }>;

const EMOJI_COOLDOWN_MS = 1500;
/** Finished games stay in memory a little so late reconnects still see the result. */
const LINGER_MS = 60_000;
const SETTLE_ATTEMPTS = 4;

export interface GameDeps {
  db: Db;
  hub: Hub;
  store: SnapshotStore;
  ledger: Ledger;
  settlement: SettlementService;
  log: FastifyBaseLogger;
  onFinished: (roomId: string, result: GameResultDto | null) => void;
}

/** One live game: the only place where its GameState changes. */
export class GameRunner {
  readonly queue = new SerialQueue();
  private timer: NodeJS.Timeout | null = null;
  private moves: Prisma.GameMoveCreateManyInput[] = [];
  private flushTimer: NodeJS.Timeout | null = null;
  private lastEmoji = new Map<string, number>();
  result: GameResultDto | null = null;

  constructor(
    private snap: GameSnapshot,
    private readonly players: PlayerInfo[],
    private readonly deps: GameDeps,
  ) {}

  get id(): string {
    return this.snap.gameId;
  }
  get roomId(): string {
    return this.snap.roomId;
  }
  get state(): GameState {
    return this.snap.state;
  }
  hasPlayer(userId: string): boolean {
    return this.snap.state.players.some((p) => p.id === userId);
  }

  resume(): void {
    this.schedule();
    this.broadcastState();
  }

  // ── player input ───────────────────────────────────────────

  async handle(userId: string, msg: GameMessage): Promise<void> {
    switch (msg.type) {
      case 'PLAY_CARD':
        return this.act(userId, { type: 'PLAY_CARD', card: msg.card, target: msg.target });
      case 'PLAY_CARDS':
        return this.act(userId, { type: 'PLAY_CARDS', cards: msg.cards });
      case 'TRANSFER':
        return this.act(userId, { type: 'TRANSFER', card: msg.card });
      case 'TAKE_CARDS':
        return this.act(userId, { type: 'TAKE_CARDS' });
      case 'PASS':
        return this.act(userId, { type: 'PASS' });
      case 'LEAVE_GAME':
        return this.act(userId, { type: 'LEAVE_GAME' });
      case 'REPORT_CHEAT':
        return this.act(userId, { type: 'REPORT_CHEAT', seq: msg.seq });
      case 'UNDO_MOVE':
        return this.undo(userId);
      case 'USE_FEATURE':
        return this.useFeature(userId, msg.feature);
      case 'SEND_EMOJI':
        return this.emoji(userId, msg.emoji);
    }
  }

  private async act(userId: string, action: GameAction): Promise<void> {
    const before = this.snap.state;
    const result = applyAction(before, userId, action, Date.now());
    if (!result.ok) throw new AppError(result.error as AppErrorCode);
    const placedCard = action.type === 'PLAY_CARD' || action.type === 'PLAY_CARDS';
    await this.commit(result, userId, action, placedCard ? before : null);
  }

  /** «Вернуть карту»: coins first, then the rollback — both inside this game's queue. */
  private async undo(userId: string): Promise<void> {
    const previous = this.snap.previous;
    if (!previous) throw new AppError('CANNOT_UNDO');
    const result = undoLastMove(previous, this.snap.state, userId, Date.now());
    if (!result.ok) throw new AppError(result.error as AppErrorCode);
    await this.deps.ledger.post({
      userId,
      currency: 'COINS',
      amount: -BigInt(FEATURE_PRICES.undo),
      type: 'PURCHASE',
      source: `game:${this.id}`,
      idempotencyKey: `undo:${this.id}:${this.snap.state.version}`,
    });
    await this.commit(result, userId, { type: 'UNDO' }, null);
  }

  private async useFeature(userId: string, feature: keyof Features): Promise<void> {
    if (!this.hasPlayer(userId)) throw new AppError('FORBIDDEN');
    const current = this.features(userId);
    if (current[feature]) return;
    const premium = this.players.find((p) => p.userId === userId)?.premium ?? false;
    if (!(feature === 'hints' && premium)) {
      await this.deps.ledger.post({
        userId,
        currency: 'COINS',
        amount: -BigInt(FEATURE_PRICES[feature]),
        type: 'PURCHASE',
        source: `game:${this.id}`,
        idempotencyKey: `feature:${this.id}:${userId}:${feature}`,
      });
    }
    this.snap.features[userId] = { ...current, [feature]: true };
    await this.persist();
    this.sendState(userId);
  }

  private emoji(userId: string, emoji: string): void {
    if (!this.hasPlayer(userId)) throw new AppError('FORBIDDEN');
    const now = Date.now();
    if (now - (this.lastEmoji.get(userId) ?? 0) < EMOJI_COOLDOWN_MS) throw new AppError('RATE_LIMITED');
    this.lastEmoji.set(userId, now);
    for (const p of this.players) this.deps.hub.send(p.userId, { type: 'EMOJI', gameId: this.id, userId, emoji });
  }

  // ── state changes ──────────────────────────────────────────

  private async commit(
    result: Extract<ActionResult, { ok: true }>,
    userId: string | null,
    action: GameAction | { type: 'UNDO' } | { type: 'TIMEOUT' },
    previous: GameState | null,
  ): Promise<void> {
    this.snap.state = result.state;
    this.snap.previous = previous;
    for (const event of result.events) {
      if (event.type === 'CARD_TRANSFERRED') {
        this.snap.transfers[event.playerId] = (this.snap.transfers[event.playerId] ?? 0) + 1;
      }
    }
    this.moves.push({ gameId: this.id, seq: result.state.version, userId, action: action as Prisma.InputJsonValue });
    this.scheduleFlush();
    await this.persist();

    this.broadcastEvents(result.events);
    this.broadcastState();

    if (result.state.status === 'finished') await this.finish();
    else this.schedule();
  }

  private schedule(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    const deadline = this.snap.state.turnDeadline;
    if (this.snap.state.status !== 'playing' || deadline === null) return;
    this.timer = setTimeout(() => {
      this.queue.run(() => this.onTimeout()).catch((error) => this.deps.log.error({ err: error, gameId: this.id }, 'timeout failed'));
    }, Math.max(0, deadline - Date.now()) + 50);
  }

  private async onTimeout(): Promise<void> {
    const result = applyTimeout(this.snap.state, Date.now());
    if (!result) return this.schedule();
    if (!result.ok) return;
    await this.commit(result, null, { type: 'TIMEOUT' }, null);
  }

  private async finish(): Promise<void> {
    if (this.timer) clearTimeout(this.timer);
    await this.flushMoves();
    try {
      this.result = await this.settle();
    } catch (error) {
      // The snapshot stays in the store: the next boot retries settlement.
      metrics.inc('arena_settlement_failures_total', 'Games whose settlement failed');
      this.deps.log.error({ err: error, gameId: this.id }, 'settlement failed');
      return;
    }
    metrics.inc('arena_games_finished_total', 'Games settled', { kind: this.result.kind, reason: this.result.reason ?? 'draw' });
    this.deps.log.info(
      { gameId: this.id, roomId: this.roomId, kind: this.result.kind, reason: this.result.reason, moves: this.snap.state.version, ms: Date.now() - this.snap.startedAt },
      'game finished',
    );
    for (const p of this.players) this.deps.hub.send(p.userId, { type: 'GAME_FINISHED', gameId: this.id, result: this.result });
    await this.deps.store.deleteGame(this.id).catch(() => undefined);
    this.deps.onFinished(this.roomId, this.result);
  }

  /** Settlement is idempotent, so a transient database error is retried a few times. */
  private async settle(): Promise<GameResultDto> {
    const input = { gameId: this.id, stake: this.snap.stake, state: this.snap.state, startedAt: this.snap.startedAt, transfers: this.snap.transfers };
    for (let attempt = 1; ; attempt++) {
      try {
        return await this.deps.settlement.finish(input);
      } catch (error) {
        if (attempt >= SETTLE_ATTEMPTS || error instanceof NotSettleable) throw error;
        this.deps.log.warn({ err: error, gameId: this.id, attempt }, 'settlement retry');
        await new Promise((resolve) => setTimeout(resolve, 500 * 2 ** attempt));
      }
    }
  }

  /** Settles a game that was already over when the process restarted. */
  async settleRecovered(): Promise<void> {
    await this.finish();
  }

  // ── outgoing ───────────────────────────────────────────────

  private features(userId: string): Features {
    return this.snap.features[userId] ?? { hints: false, discardReminder: false };
  }

  sendState(userId: string): void {
    const features = this.features(userId);
    const info = this.playerInfo();
    const premium = info.find((p) => p.userId === userId)?.premium ?? false;
    const state = toPlayerView(this.snap.state, userId, { hints: features.hints || premium, discard: features.discardReminder });
    const move = this.snap.state.lastMove;
    this.deps.hub.send(userId, {
      type: 'GAME_STATE',
      state,
      players: info,
      features: {
        hints: features.hints || premium,
        discardReminder: features.discardReminder,
        canUndo: Boolean(this.snap.previous && move?.playerId === userId && move.version === this.snap.state.version),
      },
    });
    if (this.result) this.deps.hub.send(userId, { type: 'GAME_FINISHED', gameId: this.id, result: this.result });
  }

  private broadcastState(): void {
    for (const p of this.players) this.sendState(p.userId);
  }

  private broadcastEvents(events: GameEvent[]): void {
    const message = { type: 'GAME_EVENTS', gameId: this.id, version: this.snap.state.version, events } as const;
    for (const p of this.players) this.deps.hub.send(p.userId, message);
  }

  playerInfo(): PlayerInfo[] {
    return this.players.map((p) => ({ ...p, connected: this.deps.hub.isOnline(p.userId) }));
  }

  // ── persistence ────────────────────────────────────────────

  private async persist(): Promise<void> {
    await this.deps.store.saveGame(this.snap).catch((error) => this.deps.log.error({ err: error }, 'snapshot failed'));
  }

  private scheduleFlush(): void {
    if (this.flushTimer) return;
    this.flushTimer = setTimeout(() => void this.flushMoves(), 2000);
  }

  async flushMoves(): Promise<void> {
    if (this.flushTimer) clearTimeout(this.flushTimer);
    this.flushTimer = null;
    const batch = this.moves;
    this.moves = [];
    if (!batch.length) return;
    await this.deps.db.gameMove.createMany({ data: batch, skipDuplicates: true }).catch((error) => {
      this.deps.log.error({ err: error, gameId: this.id }, 'move log write failed');
    });
  }

  dispose(): void {
    if (this.timer) clearTimeout(this.timer);
    if (this.flushTimer) clearTimeout(this.flushTimer);
  }
}

export class GameManager {
  private readonly runners = new Map<string, GameRunner>();

  constructor(private readonly deps: GameDeps) {}

  get(id: string): GameRunner | undefined {
    return this.runners.get(id);
  }

  forUser(userId: string): GameRunner | undefined {
    for (const runner of this.runners.values()) if (!runner.result && runner.hasPlayer(userId)) return runner;
    return undefined;
  }

  count(): number {
    return this.runners.size;
  }

  /** Deals, escrows stakes and starts the clock. Throws ShortOfFunds when a player cannot pay. */
  async start(room: Room): Promise<GameRunner> {
    const gameId = randomUUID();
    const now = Date.now();
    const { state } = createGame({
      gameId,
      settings: room.settings,
      playerIds: room.seats.map((s) => s.userId),
      random: cryptoRandom,
      now,
    });
    const initialDeck = [...state.players.flatMap((p) => p.hand), ...state.deck];
    await this.deps.settlement.start({ gameId, roomId: room.id, stake: room.settings.stake, state, initialDeck });

    const players: PlayerInfo[] = room.seats.map((s) => ({
      userId: s.userId,
      name: s.name,
      photoUrl: s.photoUrl,
      rating: s.rating,
      premium: s.premium,
      frame: s.frame,
      crown: s.crown,
      connected: true,
    }));
    const snapshot: GameSnapshot = { gameId, roomId: room.id, stake: room.settings.stake, state, previous: null, features: {}, transfers: {}, startedAt: now };
    const runner = this.add(snapshot, players);
    await this.deps.store.saveGame(snapshot);
    metrics.inc('arena_games_started_total', 'Games dealt', { players: String(players.length), stake: String(room.settings.stake) });
    this.deps.log.info({ gameId, roomId: room.id, players: players.length, stake: room.settings.stake }, 'game started');
    for (const p of players) this.deps.hub.send(p.userId, { type: 'GAME_STARTED', roomId: room.id, gameId, players: runner.playerInfo() });
    runner.resume();
    return runner;
  }

  /** Re-creates a runner from a stored snapshot after a restart. */
  async restore(snapshot: GameSnapshot, players: PlayerInfo[]): Promise<void> {
    const runner = this.add(snapshot, players);
    if (snapshot.state.status === 'finished') await runner.queue.run(() => runner.settleRecovered());
    else runner.resume();
  }

  private add(snapshot: GameSnapshot, players: PlayerInfo[]): GameRunner {
    const runner = new GameRunner(snapshot, players, {
      ...this.deps,
      onFinished: (roomId, result) => {
        this.deps.onFinished(roomId, result);
        setTimeout(() => {
          runner.dispose();
          this.runners.delete(snapshot.gameId);
        }, LINGER_MS).unref();
      },
    });
    this.runners.set(snapshot.gameId, runner);
    return runner;
  }

  async handle(userId: string, msg: GameMessage): Promise<void> {
    const runner = this.runners.get(msg.gameId);
    if (!runner || !runner.hasPlayer(userId)) throw new AppError('NOT_FOUND');
    await runner.queue.run(() => runner.handle(userId, msg));
  }

  async shutdown(): Promise<void> {
    for (const runner of this.runners.values()) {
      await runner.flushMoves();
      runner.dispose();
    }
  }
}

export function wsError(code: AppErrorCode, rid?: string) {
  return { type: 'ERROR' as const, rid, code, message: errorText(code) };
}
