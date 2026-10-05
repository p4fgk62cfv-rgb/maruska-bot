import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { Worker } from 'node:worker_threads';
import { DEFAULT_PARAMS, sanitizeParams, type BrainParams } from '@arena/game-engine';
import type { FastifyBaseLogger } from 'fastify';
import type { Db } from '../db.js';
import type { Prisma } from '../generated/prisma/client.js';
import { BRAIN_KEY, type Brain } from './brain.js';
import { TRAINING_TABLES, type TrainerInit, type TrainerMessage, type TrainingStats } from './training.js';

const STATS_KEY = 'bot_training';
const MOSCOW_MS = 3 * 3600_000;
const today = () => new Date(Date.now() + MOSCOW_MS).toISOString().slice(0, 10);

export interface TrainerOptions {
  /** Share of one CPU core the training may use (0.05…0.9). */
  duty: number;
  dealsPerGeneration?: number;
  examEveryMs?: number;
  examGames?: number;
  examIterations?: number;
}

/**
 * Self-play training: in a background thread three tables play day and night. A slightly changed
 * copy of the bot plays the current champion; when it wins clearly over many mirrored deals, it
 * becomes the champion and the live strong bots get its weights. Every so often an exam pits the
 * strong bot against the old «максимальный» to show progress.
 */
export class Trainer {
  private worker: Worker | null = null;
  private stats: TrainingStats | null = null;
  private saveTimer: NodeJS.Timeout | null = null;
  private stopped = false;
  /** Who plays at the watched tables: the champion and the copy being tried now. */
  current: { champion: BrainParams; challenger: BrainParams; version: number } | null = null;

  constructor(
    private readonly db: Db,
    private readonly brain: Brain,
    private readonly log: FastifyBaseLogger,
    private readonly options: TrainerOptions,
  ) {}

  /** Starts the thread when the built worker exists (production); a no-op in tests and `tsx`. */
  async start(): Promise<boolean> {
    const file = new URL('./train.worker.js', import.meta.url);
    if (!existsSync(fileURLToPath(file))) return false;
    this.stopped = false;
    this.stats = await this.load();
    this.stats.running = true;
    const brainRow = await this.db.setting.findUnique({ where: { key: BRAIN_KEY } });
    const stored = brainRow?.value as { version?: number; params?: unknown; sigma?: number } | null;
    const init: TrainerInit = {
      champion: stored?.params ? sanitizeParams(stored.params) : DEFAULT_PARAMS,
      version: stored?.version ?? 0,
      sigma: stored?.sigma,
      duty: this.options.duty,
      dealsPerGeneration: this.options.dealsPerGeneration ?? 100,
      examEveryMs: this.options.examEveryMs ?? 30 * 60_000,
      examGames: this.options.examGames ?? 40,
      examIterations: this.options.examIterations ?? 60,
    };
    this.spawn(file, init);
    this.saveTimer = setInterval(() => void this.save().catch((err: unknown) => this.log.warn({ err }, 'training stats not saved')), 60_000);
    this.saveTimer.unref();
    return true;
  }

  async stop(): Promise<void> {
    this.stopped = true;
    if (this.saveTimer) clearInterval(this.saveTimer);
    if (this.stats) this.stats.running = false;
    await this.save().catch(() => undefined);
    await this.worker?.terminate();
    this.worker = null;
  }

  /** For «Управление»: what the stored stats say (another server may be the one training). */
  async read(): Promise<TrainingStats> {
    return this.stats ?? (await this.load());
  }

  private spawn(file: URL, init: TrainerInit): void {
    const worker = new Worker(file, { workerData: init });
    this.worker = worker;
    worker.on('message', (m: TrainerMessage) => void this.onMessage(m).catch((err: unknown) => this.log.warn({ err }, 'training update failed')));
    worker.on('error', (err) => this.log.error({ err }, 'training thread failed'));
    worker.on('exit', (code) => {
      if (this.stopped) return;
      this.log.warn({ code }, 'training thread stopped; restarting in a minute');
      setTimeout(() => {
        if (!this.stopped) void this.start().catch(() => undefined);
      }, 60_000).unref();
    });
  }

  private async onMessage(m: TrainerMessage): Promise<void> {
    const stats = this.stats;
    if (!stats) return;
    if (m.type === 'challenger') {
      this.current = { champion: m.champion, challenger: m.params, version: m.version };
      return;
    }
    if (m.type === 'error') {
      this.log.error({ err: m.error }, 'training failed');
      return;
    }
    if (m.type === 'exam') {
      stats.exams = [...stats.exams, { ...m.exam, version: m.version }].slice(-48);
      this.log.info({ version: m.version, winRate: m.exam.winRate, games: m.exam.games }, 'bot exam against the old hard bot');
      await this.save();
      return;
    }
    const played = m.games.reduce((s, n) => s + n, 0);
    stats.games += played;
    const day = today();
    stats.today = stats.today.day === day ? { day, games: stats.today.games + played } : { day, games: played };
    stats.generations++;
    stats.sigma = m.sigma;
    TRAINING_TABLES.forEach((t, i) => {
      const row = stats.tables.find((x) => x.key === t.key);
      if (row) row.games += m.games[i] ?? 0;
    });
    if (m.promoted && m.params) {
      stats.improvements++;
      stats.version = m.version;
      stats.lastImprovementAt = new Date().toISOString();
      stats.history = [...stats.history, { at: stats.lastImprovementAt, version: m.version, score: m.score }].slice(-100);
      const value = { version: m.version, params: m.params, sigma: m.sigma, updatedAt: stats.lastImprovementAt } as unknown as Prisma.InputJsonValue;
      await this.db.setting.upsert({ where: { key: BRAIN_KEY }, create: { key: BRAIN_KEY, value }, update: { value } });
      this.brain.params = m.params;
      this.brain.version = m.version;
      this.log.info({ version: m.version, score: m.score }, 'bot brain improved');
      await this.save();
    }
  }

  private async load(): Promise<TrainingStats> {
    const row = await this.db.setting.findUnique({ where: { key: STATS_KEY } });
    const v = (row?.value ?? {}) as Partial<TrainingStats>;
    return {
      running: false,
      version: v.version ?? this.brain.version,
      startedAt: v.startedAt ?? new Date().toISOString(),
      games: v.games ?? 0,
      today: v.today?.day === today() ? v.today : { day: today(), games: 0 },
      generations: v.generations ?? 0,
      improvements: v.improvements ?? 0,
      lastImprovementAt: v.lastImprovementAt ?? null,
      sigma: v.sigma ?? 0.25,
      tables: TRAINING_TABLES.map((t) => ({ key: t.key, title: t.title, games: v.tables?.find((x) => x.key === t.key)?.games ?? 0 })),
      exams: v.exams ?? [],
      history: v.history ?? [],
    };
  }

  private async save(): Promise<void> {
    if (!this.stats) return;
    const value = this.stats as unknown as Prisma.InputJsonValue;
    await this.db.setting.upsert({ where: { key: STATS_KEY }, create: { key: STATS_KEY, value }, update: { value } });
  }
}
