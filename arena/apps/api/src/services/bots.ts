import type { BotLevel } from '@arena/game-engine';
import type { BotSettingsDto } from '@arena/shared';
import type { Db } from '../db.js';
import type { Ledger } from './ledger.js';

const KEY = 'bot_players';
const DEFAULTS: BotSettingsDto = { enabled: true, delaySec: 12, level: 'normal' };
/** How many bot accounts exist: enough for several full tables at once. */
const POOL = 60;
/** Bot accounts live far above real Telegram ids. */
const BOT_TG_BASE = 9_000_000_000_000n;
/** A bot tops up to at least this much credit (or ten stakes) before sitting down. */
const BANK = 5_000_000n;

const NAMES = [
  'Алексей', 'Марина', 'Дмитрий', 'Ольга', 'Сергей', 'Наталья', 'Андрей', 'Екатерина', 'Игорь', 'Светлана',
  'Максим', 'Татьяна', 'Артём', 'Юлия', 'Никита', 'Анна', 'Павел', 'Ирина', 'Роман', 'Елена',
  'Владимир', 'Ксения', 'Егор', 'Дарья', 'Олег', 'Виктория', 'Михаил', 'Алина', 'Денис', 'Полина',
  'Кирилл', 'Вероника', 'Антон', 'София', 'Глеб', 'Валерия', 'Илья', 'Карина', 'Тимур', 'Людмила',
  'Руслан', 'Ангелина', 'Вадим', 'Маргарита', 'Станислав', 'Надежда', 'Арсений', 'Евгения', 'Григорий', 'Лилия',
  'Фёдор', 'Яна', 'Борис', 'Диана', 'Леонид', 'Вера', 'Ярослав', 'Алёна', 'Константин', 'Зарина',
];

/** Bot opponents: their accounts, the owner's settings and their bank. */
export class BotService {
  private cached: { at: number; value: BotSettingsDto } | null = null;
  private ids: string[] = [];

  constructor(private readonly db: Db, private readonly ledger: Ledger) {}

  async settings(): Promise<BotSettingsDto> {
    if (this.cached && Date.now() - this.cached.at < 30_000) return this.cached.value;
    const row = await this.db.setting.findUnique({ where: { key: KEY } });
    const value = { ...DEFAULTS, ...((row?.value as Partial<BotSettingsDto> | null) ?? {}) };
    this.cached = { at: Date.now(), value };
    return value;
  }

  async setSettings(value: BotSettingsDto): Promise<BotSettingsDto> {
    await this.db.setting.upsert({ where: { key: KEY }, create: { key: KEY, value: { ...value } }, update: { value: { ...value } } });
    this.cached = { at: Date.now(), value };
    return value;
  }

  level(): BotLevel {
    return this.cached?.value.level ?? DEFAULTS.level;
  }

  /** Creates the bot accounts once (idempotent) and remembers their ids. */
  async ensurePool(): Promise<string[]> {
    if (this.ids.length) return this.ids;
    const existing = await this.db.user.findMany({ where: { isBot: true }, select: { id: true } });
    if (existing.length < POOL) {
      for (let i = 0; i < POOL; i++) {
        const telegramId = BOT_TG_BASE + BigInt(i);
        const user = await this.db.user.upsert({
          where: { telegramId },
          create: { telegramId, firstName: NAMES[i % NAMES.length]!, isBot: true, languageCode: 'ru' },
          update: { isBot: true },
        });
        // Ratings spread like real players', so bots do not all look like beginners.
        await this.db.profile.createMany({ data: [{ userId: user.id, rating: 100 + ((i * 7919) % 4000) }], skipDuplicates: true });
        await this.db.wallet.createMany({ data: (['CREDITS', 'COINS', 'DIAMONDS'] as const).map((currency) => ({ userId: user.id, currency })), skipDuplicates: true });
      }
    }
    this.ids = (await this.db.user.findMany({ where: { isBot: true }, select: { id: true } })).map((u) => u.id);
    return this.ids;
  }

  isBot(userId: string): boolean {
    return this.ids.includes(userId);
  }

  /** Free bots in random order: not sitting at any table. */
  async pick(count: number, busy: Set<string>): Promise<string[]> {
    const pool = (await this.ensurePool()).filter((id) => !busy.has(id));
    for (let i = pool.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [pool[i], pool[j]] = [pool[j]!, pool[i]!];
    }
    return pool.slice(0, count);
  }

  /** A bot always has enough for the stake: the house tops it up (recorded in the ledger). */
  async fund(userId: string, stake: number): Promise<void> {
    const wallet = await this.db.wallet.findUnique({ where: { userId_currency: { userId, currency: 'CREDITS' } } });
    const need = BigInt(stake) * 10n > BANK ? BigInt(stake) * 10n : BANK;
    const balance = wallet?.balance ?? 0n;
    if (balance >= BigInt(stake)) return;
    await this.ledger.post({
      userId,
      currency: 'CREDITS',
      amount: need - balance,
      type: 'ADMIN',
      source: 'bot-bank',
      idempotencyKey: `botbank:${userId}:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`,
    });
  }
}
