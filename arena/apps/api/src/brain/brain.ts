import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { Worker } from 'node:worker_threads';
import {
  DEFAULT_PARAMS,
  candidates,
  policyMove,
  sanitizeParams,
  searchMove,
  visibleCheats,
  type BrainMove,
  type BrainParams,
  type CardMemory,
  type GameState,
  type PlayerId,
  type VoidNote,
} from '@arena/game-engine';
import type { FastifyBaseLogger } from 'fastify';
import type { Db } from '../db.js';

export interface ThinkRequest {
  id: number;
  state: GameState;
  me: PlayerId;
  memory: CardMemory;
  notes: VoidNote[];
  params: BrainParams;
  budgetMs: number;
  iterations: number;
}
export interface ThinkReply {
  id: number;
  move: BrainMove | null;
  error?: string;
}

/** The trained weights live here; the trainer writes a new version when it finds a better one. */
export const BRAIN_KEY = 'bot_brain';

/**
 * The strong («максимальный») bots' thinking: a search over guessed deals with the weights
 * found by self-play. In production it runs in worker threads; without the built worker file
 * (tests, `tsx` in development) it thinks inline with a small budget.
 */
export class Brain {
  params: BrainParams = DEFAULT_PARAMS;
  version = 0;
  private readonly workers: { worker: Worker; busy: boolean }[] = [];
  private readonly waiting: { req: ThinkRequest; resolve: (m: BrainMove | null) => void }[] = [];
  private readonly pending = new Map<number, { resolve: (m: BrainMove | null) => void; timer: NodeJS.Timeout; slot: { worker: Worker; busy: boolean } }>();
  private nextId = 1;
  private refreshTimer: NodeJS.Timeout | null = null;

  constructor(
    private readonly db: Db,
    private readonly log: FastifyBaseLogger,
    private readonly threads: number,
    /** Search size when thinking inline (tests). */
    private readonly inlineIterations = 12,
  ) {}

  async start(): Promise<void> {
    await this.reload();
    this.refreshTimer = setInterval(() => void this.reload().catch(() => undefined), 60_000);
    this.refreshTimer.unref();
    const file = new URL('./think.worker.js', import.meta.url);
    if (this.threads > 0 && existsSync(fileURLToPath(file))) {
      for (let i = 0; i < this.threads; i++) this.spawn(file);
    }
  }

  async stop(): Promise<void> {
    if (this.refreshTimer) clearInterval(this.refreshTimer);
    for (const p of this.pending.values()) {
      clearTimeout(p.timer);
      p.resolve(null);
    }
    this.pending.clear();
    await Promise.all(this.workers.map((w) => w.worker.terminate()));
    this.workers.length = 0;
  }

  /** Latest trained weights (the trainer may have found better ones). */
  async reload(): Promise<void> {
    const row = await this.db.setting.findUnique({ where: { key: BRAIN_KEY } });
    const value = row?.value as { version?: number; params?: unknown } | null;
    if (value?.params) {
      this.params = sanitizeParams(value.params);
      this.version = value.version ?? 0;
    }
  }

  /** Something to do for this bot right now (a quick check, no search). */
  hasMove(state: GameState, me: PlayerId): boolean {
    return visibleCheats(state, me).length > 0 || candidates(state, me, this.params).length > 0;
  }

  /** The move after thinking up to `budgetMs`. Never throws: on trouble, the policy's own choice. */
  think(state: GameState, me: PlayerId, memory: CardMemory, budgetMs: number, notes: VoidNote[] = []): Promise<BrainMove | null> {
    const fallback = () => policyMove(state, me, this.params, Math.random, 0.02);
    if (!this.workers.length) {
      try {
        return Promise.resolve(searchMove(state, me, memory, this.params, { iterations: this.inlineIterations, budgetMs: Math.min(budgetMs, 150), notes }));
      } catch {
        return Promise.resolve(fallback());
      }
    }
    const req: ThinkRequest = { id: this.nextId++, state, me, memory, notes, params: this.params, budgetMs, iterations: 4000 };
    return new Promise<BrainMove | null>((resolve) => {
      this.waiting.push({ req, resolve: (m) => resolve(m ?? fallback()) });
      this.dispatch();
    });
  }

  private spawn(file: URL): void {
    const worker = new Worker(file);
    const slot = { worker, busy: false };
    worker.on('message', (reply: ThinkReply) => {
      const p = this.pending.get(reply.id);
      if (reply.error) this.log.warn({ err: reply.error }, 'bot search failed');
      slot.busy = false;
      if (p) {
        clearTimeout(p.timer);
        this.pending.delete(reply.id);
        p.resolve(reply.move);
      }
      this.dispatch();
    });
    worker.on('error', (err) => this.log.error({ err }, 'bot thinking thread failed'));
    worker.on('exit', () => {
      const at = this.workers.indexOf(slot);
      if (at >= 0) this.workers.splice(at, 1);
      for (const [id, p] of this.pending) {
        if (p.slot !== slot) continue;
        clearTimeout(p.timer);
        this.pending.delete(id);
        p.resolve(null);
      }
      if (this.refreshTimer) setTimeout(() => this.spawn(file), 1000).unref();
    });
    this.workers.push(slot);
  }

  private dispatch(): void {
    for (const slot of this.workers) {
      if (slot.busy) continue;
      const next = this.waiting.shift();
      if (!next) return;
      slot.busy = true;
      // A thread that does not answer in time: the bot plays the policy's move instead.
      const timer = setTimeout(() => {
        this.pending.delete(next.req.id);
        next.resolve(null);
      }, next.req.budgetMs + 2000);
      this.pending.set(next.req.id, { resolve: next.resolve, timer, slot });
      slot.worker.postMessage(next.req);
    }
  }
}
