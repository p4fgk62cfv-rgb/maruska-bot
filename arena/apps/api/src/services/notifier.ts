import type { FastifyBaseLogger } from 'fastify';
import type { Db } from '../db.js';
import type { Prisma } from '../generated/prisma/client.js';

export interface BotMessage {
  text: string;
  /** Inline button that opens a link (the Mini App deep link). */
  button?: { text: string; url: string };
}

export type SendOutcome = 'ok' | 'blocked' | 'retry';

/** Minimal Telegram Bot API client. Uses the same token as the Python bot: sendMessage does not clash with its polling. */
export class TelegramBot {
  constructor(
    private readonly token: string,
    private readonly apiUrl = 'https://api.telegram.org',
    private readonly http: typeof fetch = fetch,
  ) {}

  async send(chatId: bigint, message: BotMessage): Promise<SendOutcome> {
    const body = {
      chat_id: chatId.toString(),
      text: message.text,
      parse_mode: 'HTML',
      disable_web_page_preview: true,
      ...(message.button ? { reply_markup: { inline_keyboard: [[{ text: message.button.text, url: message.button.url }]] } } : {}),
    };
    try {
      const res = await this.http(`${this.apiUrl}/bot${this.token}/sendMessage`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (res.ok) return 'ok';
      // 400 chat not found / 403 blocked: the user has no private chat with the bot.
      return res.status === 400 || res.status === 403 ? 'blocked' : 'retry';
    } catch {
      return 'retry';
    }
  }
}

const MAX_ATTEMPTS = 5;

/**
 * Transactional outbox for bot messages: a row is written first, then delivered. Failed rows
 * are retried by a background sweep, so a Telegram hiccup or a restart never loses an invite.
 */
export class Outbox {
  private timer: NodeJS.Timeout | null = null;
  private sweeping = false;

  constructor(
    private readonly db: Db,
    private readonly bot: TelegramBot | null,
    private readonly log: FastifyBaseLogger,
  ) {}

  async enqueue(userId: string, kind: string, message: BotMessage): Promise<void> {
    const row = await this.db.notification.create({ data: { userId, kind, payload: message as unknown as Prisma.InputJsonValue } });
    void this.deliver(row.id);
  }

  start(intervalMs = 15_000): void {
    this.timer = setInterval(() => void this.sweep(), intervalMs);
    this.timer.unref();
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
  }

  async sweep(): Promise<void> {
    if (this.sweeping) return;
    this.sweeping = true;
    try {
      const pending = await this.db.notification.findMany({
        where: { sentAt: null, attempts: { lt: MAX_ATTEMPTS }, createdAt: { gt: new Date(Date.now() - 24 * 3600_000) } },
        orderBy: { createdAt: 'asc' },
        take: 20,
        select: { id: true },
      });
      for (const { id } of pending) await this.deliver(id);
    } finally {
      this.sweeping = false;
    }
  }

  private async deliver(id: string): Promise<void> {
    if (!this.bot) return;
    const row = await this.db.notification.findUnique({ where: { id }, include: { user: { select: { telegramId: true } } } });
    if (!row || row.sentAt) return;
    const outcome = await this.bot.send(row.user.telegramId, row.payload as unknown as BotMessage);
    await this.db.notification.update({
      where: { id },
      data:
        outcome === 'ok'
          ? { sentAt: new Date(), attempts: { increment: 1 }, lastError: null }
          : outcome === 'blocked'
            ? { sentAt: new Date(), attempts: { increment: 1 }, lastError: 'blocked' }
            : { attempts: { increment: 1 }, lastError: 'retry' },
    });
    if (outcome === 'retry') this.log.warn({ notificationId: id }, 'bot message delivery failed, will retry');
  }
}
