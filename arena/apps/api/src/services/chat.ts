import { CHAT, censor, hasLink, type ChatMessageDto, type ChatStateDto, type ServerMessage } from '@arena/shared';
import type { FastifyBaseLogger } from 'fastify';
import type { Db } from '../db.js';
import type { Profile, User } from '../generated/prisma/client.js';
import { AppError } from '../lib/errors.js';
import type { Outbox } from './notifier.js';
import { publicUser } from './users.js';

export interface ChatDeps {
  db: Db;
  /** Pushes to everyone who has the chat open. */
  publish: (message: ServerMessage) => void;
  online: () => number;
  /** Telegram ids of the owners (OWNER_IDS): the chat's moderators. */
  owners: ReadonlySet<bigint>;
  outbox: Outbox;
  log: FastifyBaseLogger;
}

type Author = User & { profile: Profile | null };
type Row = {
  id: string;
  text: string;
  createdAt: Date;
  user: Author;
  replyTo?: { id: string; text: string; deletedAt: Date | null; user: Author } | null;
};
/** Everything a message needs to be shown: its author and the message it answers. */
const WITH = { user: { include: { profile: true } }, replyTo: { include: { user: { include: { profile: true } } } } } as const;

/**
 * The Arena's common chat. Written to over REST, pushed over the socket.
 * Swearing is masked, links are refused, a player writes after the first game and not
 * faster than CHAT.gapMs / CHAT.perMinute. Owners delete messages and mute players;
 * three reports from different players hide a message on their own.
 */
export class ChatService {
  /** Send times of the last minute, per player. Lost on restart, which is fine for a flood guard. */
  private readonly sent = new Map<string, number[]>();
  private timer: NodeJS.Timeout | null = null;

  constructor(private readonly deps: ChatDeps) {}

  private isOwner(telegramId: bigint): boolean {
    return this.deps.owners.has(telegramId);
  }

  start(): void {
    this.timer = setInterval(() => void this.cleanup().catch((err: unknown) => this.deps.log.warn({ err }, 'chat cleanup failed')), 3600_000);
    this.timer.unref();
    void this.cleanup().catch(() => undefined);
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
  }

  async state(userId: string, before?: string): Promise<ChatStateDto> {
    const { db } = this.deps;
    const [rows, me] = await Promise.all([
      db.chatMessage.findMany({
        where: { deletedAt: null, ...(before ? { id: { lt: before } } : {}) },
        orderBy: { id: 'desc' },
        take: CHAT.page + 1,
        include: WITH,
      }),
      db.user.findUnique({ where: { id: userId }, include: { profile: true } }),
    ]);
    const more = rows.length > CHAT.page;
    const page = rows.slice(0, CHAT.page).reverse();
    const moderator = me ? this.isOwner(me.telegramId) : false;
    return {
      messages: page.map(dto),
      more,
      blocked: me && !moderator ? blocked(me.profile) : null,
      moderator,
      online: this.deps.online(),
    };
  }

  async send(userId: string, raw: string, replyTo?: string): Promise<ChatMessageDto> {
    const text = raw.replace(/\s+/g, ' ').trim();
    if (!text || text.length > CHAT.maxLength) throw new AppError('VALIDATION_FAILED');
    const { db } = this.deps;
    const me = await db.user.findUnique({ where: { id: userId }, include: { profile: true } });
    if (!me?.profile) throw new AppError('UNAUTHORIZED');
    if (!this.isOwner(me.telegramId)) {
      const why = blocked(me.profile);
      if (why) throw new AppError(why.reason === 'muted' ? 'CHAT_MUTED' : 'CHAT_NEED_GAME');
    }
    if (hasLink(text)) throw new AppError('CHAT_LINKS');
    this.throttle(userId);

    // A reply to a message that is gone (deleted or expired) goes out as a plain message.
    const target = replyTo ? await db.chatMessage.findFirst({ where: { id: replyTo, deletedAt: null }, select: { id: true } }) : null;
    const row = await db.chatMessage.create({ data: { userId, text: censor(text), replyToId: target?.id ?? null }, include: WITH });
    const message = dto(row);
    this.deps.publish({ type: 'CHAT_MESSAGE', message });
    return message;
  }

  /** Any player: one report per message; enough of them hide it. The owners hear of the first one. */
  async report(userId: string, messageId: string): Promise<void> {
    const { db } = this.deps;
    const message = await db.chatMessage.findUnique({ where: { id: messageId }, include: { user: { include: { profile: true } } } });
    if (!message || message.deletedAt) return;
    if (message.userId === userId) throw new AppError('VALIDATION_FAILED');
    const created = await db.chatReport.createMany({ data: [{ messageId, reporterId: userId }], skipDuplicates: true });
    if (!created.count) return;
    const reports = await db.chatReport.count({ where: { messageId } });
    if (reports >= CHAT.reportsToHide) await this.hide([messageId]);
    if (reports === 1 || reports === CHAT.reportsToHide) {
      const who = publicUser(message.user, message.user.profile!).name;
      const hidden = reports >= CHAT.reportsToHide ? '\nСообщение скрыто автоматически: жалоб от разных игроков — ' + reports + '.' : '';
      await this.tellOwners(`🚩 Жалоба в общем чате Арены\n${who}: «${message.text}»${hidden}\n\nУдалить сообщение или запретить писать можно в самом чате: нажмите на сообщение.`);
    }
  }

  /** Owner: delete one message. */
  async remove(ownerId: string, messageId: string): Promise<void> {
    await this.requireOwner(ownerId);
    await this.hide([messageId]);
  }

  /** Owner: no writing for `hours` (0 gives the right back); `purge` also hides the player's messages of the last day. */
  async mute(ownerId: string, userId: string, hours: number, purge: boolean): Promise<string | null> {
    await this.requireOwner(ownerId);
    const { db } = this.deps;
    const until = hours > 0 ? new Date(Date.now() + hours * 3600_000) : null;
    const updated = await db.profile.updateMany({ where: { userId }, data: { chatMutedUntil: until } });
    if (!updated.count) throw new AppError('NOT_FOUND');
    if (purge) {
      const rows = await db.chatMessage.findMany({ where: { userId, deletedAt: null, createdAt: { gte: new Date(Date.now() - 24 * 3600_000) } }, select: { id: true } });
      await this.hide(rows.map((r) => r.id));
    }
    return until?.toISOString() ?? null;
  }

  /** Newest message time, for the «new» mark on the home screen. */
  async lastAt(): Promise<string | null> {
    const row = await this.deps.db.chatMessage.findFirst({ where: { deletedAt: null }, orderBy: { id: 'desc' }, select: { createdAt: true } });
    return row?.createdAt.toISOString() ?? null;
  }

  async cleanup(now = Date.now()): Promise<number> {
    const { count } = await this.deps.db.chatMessage.deleteMany({ where: { createdAt: { lt: new Date(now - CHAT.keepDays * 24 * 3600_000) } } });
    return count;
  }

  private async hide(ids: string[]): Promise<void> {
    if (!ids.length) return;
    const { count } = await this.deps.db.chatMessage.updateMany({ where: { id: { in: ids }, deletedAt: null }, data: { deletedAt: new Date() } });
    if (count) this.deps.publish({ type: 'CHAT_DELETED', ids });
  }

  private async requireOwner(userId: string): Promise<void> {
    const user = await this.deps.db.user.findUnique({ where: { id: userId }, select: { telegramId: true } });
    if (!user || !this.isOwner(user.telegramId)) throw new AppError('FORBIDDEN');
  }

  private throttle(userId: string, now = Date.now()): void {
    const recent = (this.sent.get(userId) ?? []).filter((t) => now - t < 60_000);
    if (recent.length && now - recent[recent.length - 1]! < CHAT.gapMs) throw new AppError('CHAT_TOO_FAST');
    if (recent.length >= CHAT.perMinute) throw new AppError('CHAT_TOO_FAST');
    recent.push(now);
    this.sent.set(userId, recent);
    if (this.sent.size > 5000) {
      for (const [id, times] of this.sent) if (!times.some((t) => now - t < 60_000)) this.sent.delete(id);
    }
  }

  private async tellOwners(text: string): Promise<void> {
    const owners = await this.deps.db.user.findMany({ where: { telegramId: { in: [...this.deps.owners] } }, select: { id: true } });
    for (const u of owners) await this.deps.outbox.enqueue(u.id, 'chat_report', { text }).catch(() => undefined);
  }
}

function blocked(profile: Profile | null): ChatStateDto['blocked'] {
  if (!profile) return { reason: 'games', until: null };
  if (profile.chatMutedUntil && profile.chatMutedUntil.getTime() > Date.now()) return { reason: 'muted', until: profile.chatMutedUntil.toISOString() };
  if (profile.gamesPlayed < CHAT.minGames) return { reason: 'games', until: null };
  return null;
}

function dto(row: Row): ChatMessageDto {
  const quoted = row.replyTo;
  return {
    id: row.id,
    user: publicUser(row.user, row.user.profile!),
    text: row.text,
    createdAt: row.createdAt.toISOString(),
    replyTo: quoted
      ? {
          id: quoted.id,
          userId: quoted.user.id,
          name: publicUser(quoted.user, quoted.user.profile!).name,
          text: quoted.deletedAt ? null : quoted.text.length > 90 ? `${quoted.text.slice(0, 90)}…` : quoted.text,
        }
      : null,
  };
}
