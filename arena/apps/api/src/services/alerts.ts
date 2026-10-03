import type { FastifyBaseLogger } from 'fastify';
import { metrics } from '../lib/metrics.js';
import type { TelegramBot } from './notifier.js';

/** The same trouble is reported to the owners at most this often. */
const REPEAT_MS = 10 * 60_000;

/**
 * Trouble the owners must know about at once (Redis or the database failing, a game that
 * could not be settled, a crash). Goes straight to the Bot API, not through the database
 * outbox: the database itself may be what is failing. Every alert is also logged.
 */
export class Alerts {
  private readonly sent = new Map<string, number>();
  /** Kinds reported and not yet resolved: «it works again» is sent only for these. */
  private readonly open = new Set<string>();

  constructor(
    private readonly bot: TelegramBot | null,
    private readonly owners: Set<bigint>,
    private readonly log: FastifyBaseLogger,
    private readonly repeatMs = REPEAT_MS,
  ) {}

  raise(kind: string, text: string, details: Record<string, unknown> = {}): void {
    metrics.inc('arena_alerts_total', 'Owner alerts raised', { kind });
    this.log.error({ alert: kind, ...details }, text);
    this.open.add(kind);
    const now = Date.now();
    if (now - (this.sent.get(kind) ?? 0) < this.repeatMs) return;
    this.sent.set(kind, now);
    this.send(`🚨 <b>Арена</b>: ${escapeHtml(text)}`);
  }

  /** The trouble is over: the owners who were told get «fixed». */
  resolve(kind: string, text: string): void {
    if (!this.open.delete(kind)) return;
    this.log.info({ alert: kind }, text);
    this.sent.delete(kind);
    this.send(`✅ <b>Арена</b>: ${escapeHtml(text)}`);
  }

  /** Not trouble, but worth knowing (the server came back after a crash). */
  notice(kind: string, text: string): void {
    this.log.warn({ alert: kind }, text);
    const now = Date.now();
    if (now - (this.sent.get(kind) ?? 0) < this.repeatMs) return;
    this.sent.set(kind, now);
    this.send(`ℹ️ <b>Арена</b>: ${escapeHtml(text)}`);
  }

  private send(text: string): void {
    if (!this.bot) return;
    for (const owner of this.owners) {
      void this.bot.send(owner, { text }).catch(() => undefined);
    }
  }
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
