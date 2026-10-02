import { createHash, randomBytes, timingSafeEqual } from 'node:crypto';
import type { Db } from '../db.js';
import { AppError } from '../lib/errors.js';
import type { TelegramUser } from '../telegram/initData.js';
import { isBanned, type UserService } from './users.js';

/** How long the person has to confirm in the bot. */
export const LOGIN_TTL_MS = 5 * 60_000;
const ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789';

const sha256 = (value: string) => createHash('sha256').update(value).digest('hex');
const token = (length: number) => Array.from(randomBytes(length), (b) => ALPHABET[b % ALPHABET.length]).join('');

/** «alogin_<id>»: the /start parameter the bot receives. */
export function loginStartParam(id: string): string {
  return `alogin_${id}`;
}

/**
 * Sign-in for the installed app (outside Telegram). The app asks for a request and keeps its
 * secret; the person opens the bot by the request's link and confirms; the app, polling with the
 * secret, then gets a session. The link alone (shared, forwarded, seen over a shoulder) is not
 * enough: the session goes only to the device holding the secret, and only once.
 */
export class AppLoginService {
  constructor(private readonly deps: { db: Db; users: UserService }) {}

  async create(device: string | null): Promise<{ id: string; secret: string; expiresAt: number }> {
    const id = token(20);
    const secret = token(32);
    const expiresAt = new Date(Date.now() + LOGIN_TTL_MS);
    await this.deps.db.loginRequest.create({ data: { id, secretHash: sha256(secret), device: device?.slice(0, 160) ?? null, expiresAt } });
    // Old requests are cleaned up as new ones come.
    await this.deps.db.loginRequest.deleteMany({ where: { expiresAt: { lt: new Date(Date.now() - 3600_000) } } }).catch(() => undefined);
    return { id, secret, expiresAt: expiresAt.getTime() };
  }

  /** What the bot shows before the person confirms. */
  async describe(id: string): Promise<{ device: string | null; expiresAt: number; confirmed: boolean }> {
    const row = await this.deps.db.loginRequest.findUnique({ where: { id } });
    if (!row || row.expiresAt.getTime() < Date.now() || row.usedAt) throw new AppError('NOT_FOUND');
    return { device: row.device, expiresAt: row.expiresAt.getTime(), confirmed: row.confirmedAt !== null };
  }

  /** The person pressed «Войти» in the bot. */
  async confirm(id: string, tg: TelegramUser): Promise<{ name: string }> {
    const row = await this.deps.db.loginRequest.findUnique({ where: { id } });
    if (!row || row.expiresAt.getTime() < Date.now() || row.usedAt) throw new AppError('NOT_FOUND');
    if (row.confirmedAt) {
      if (row.telegramId !== BigInt(tg.id)) throw new AppError('FORBIDDEN');
      return { name: tg.first_name };
    }
    // An existing player keeps their photo and nickname; a new one gets an account like any first login.
    const user = (await this.deps.db.user.findUnique({ where: { telegramId: BigInt(tg.id) } })) ?? (await this.deps.users.upsertFromTelegram(tg));
    if (user.isBot) throw new AppError('FORBIDDEN');
    if (isBanned(user)) throw new AppError('BANNED');
    const done = await this.deps.db.loginRequest.updateMany({
      where: { id, confirmedAt: null, usedAt: null },
      data: { confirmedAt: new Date(), userId: user.id, telegramId: BigInt(tg.id) },
    });
    if (done.count === 0) throw new AppError('NOT_FOUND');
    return { name: user.firstName };
  }

  /** The app asks with its secret: null while waiting; the user (once) when confirmed. */
  async take(id: string, secret: string): Promise<{ userId: string; telegramId: bigint } | null> {
    const row = await this.deps.db.loginRequest.findUnique({ where: { id } });
    if (!row || row.usedAt) throw new AppError('NOT_FOUND');
    const given = Buffer.from(sha256(secret));
    if (!timingSafeEqual(given, Buffer.from(row.secretHash))) throw new AppError('NOT_FOUND');
    if (!row.confirmedAt) {
      if (row.expiresAt.getTime() < Date.now()) throw new AppError('NOT_FOUND');
      return null;
    }
    const used = await this.deps.db.loginRequest.updateMany({ where: { id, usedAt: null }, data: { usedAt: new Date() } });
    if (used.count === 0) throw new AppError('NOT_FOUND');
    return { userId: row.userId!, telegramId: row.telegramId! };
  }
}
