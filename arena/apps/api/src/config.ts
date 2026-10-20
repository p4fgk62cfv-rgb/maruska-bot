import { z } from 'zod';

const bool = z
  .string()
  .optional()
  .transform((v) => v === '1' || v === 'true');

const schema = z.object({
  NODE_ENV: z.enum(['development', 'production', 'test']).default('development'),
  PORT: z.coerce.number().int().default(8080),
  /** Same Postgres as the bot, with `?schema=arena`. */
  DATABASE_URL: z.string().min(1),
  REDIS_URL: z.string().optional(),
  BOT_TOKEN: z.string().min(20),
  BOT_USERNAME: z.string().default(''),
  /** Short name of the Mini App in BotFather (/newapp). Empty = the bot's main Mini App. */
  MINI_APP_SHORT_NAME: z.string().default(''),
  /** Telegram IDs (comma separated) of the game's owners: in-app announcements and gifts. Same list as the bot's OWNER_IDS. */
  OWNER_IDS: z.string().default(''),
  /** Public https address of the arena; invites from the bot open it directly. Railway's own domain when unset. */
  PUBLIC_URL: z.string().default(''),
  RAILWAY_PUBLIC_DOMAIN: z.string().default(''),
  /** Signs session tokens. At least 32 random characters. */
  SESSION_SECRET: z.string().min(32),
  SESSION_TTL_HOURS: z.coerce.number().int().positive().default(24),
  /** How old a Telegram initData may be when exchanged for a session. */
  INIT_DATA_MAX_AGE_SECONDS: z.coerce.number().int().positive().default(3600),
  /** Shared secret for bot → arena calls on /internal/*. */
  INTERNAL_API_SECRET: z.string().min(16).optional(),
  SIGNUP_BONUS_CREDITS: z.coerce.number().int().nonnegative().default(1_450),
  SIGNUP_BONUS_COINS: z.coerce.number().int().nonnegative().default(0),
  /** Seconds tournament players have to press «Готов» before a no-show loss. */
  MATCH_READY_SECONDS: z.coerce.number().int().positive().default(90),
  /** Мини-турнир группы: сколько ждать игроков у стола, потом техническое поражение. */
  MINI_TOURNAMENT_READY_SECONDS: z.coerce.number().int().min(1).max(600).default(60),
  /** Logins per minute from one IP (raise only for load tests from a single machine). */
  AUTH_RATE_LIMIT: z.coerce.number().int().positive().default(20),
  /** Postgres connections per instance; keep instances × size under the server's max_connections. */
  DB_POOL_SIZE: z.coerce.number().int().positive().default(20),
  RAKE_PERCENT: z.coerce.number().min(0).max(50).default(5),
  /** Monthly seasons start by themselves and pay the top when they end: «on» or «off». */
  AUTO_SEASONS: z.enum(['on', 'off']).default('on'),
  /** Season prizes in credits by place: «100000,50000,25000,10000x7» = 1st, 2nd, 3rd, then 7 × 10 000. */
  SEASON_PRIZES: z.string().default('100000,50000,25000,10000x7'),
  /** VIP days on top of the credits, by place: «7,3,1». */
  SEASON_VIP_DAYS: z.string().default('7,3,1'),
  /** Daily evening and weekend tournaments are announced by themselves: «on» or «off». */
  AUTO_TOURNAMENTS: z.enum(['on', 'off']).default('on'),
  /** Moscow hour of the daily free tournament; its prizes are paid by the arena. */
  DAILY_TOURNAMENT_HOUR: z.coerce.number().int().min(0).max(23).default(20),
  DAILY_TOURNAMENT_PRIZE: z.coerce.number().int().nonnegative().default(10_000),
  /** Saturday tournament at 18:00 Moscow time: entry fee plus a prize pool guaranteed by the arena. */
  WEEKEND_TOURNAMENT_FEE: z.coerce.number().int().nonnegative().default(1_000),
  WEEKEND_TOURNAMENT_PRIZE: z.coerce.number().int().nonnegative().default(50_000),
  /**
   * A tournament with prizes guaranteed by the arena starts only with this many players,
   * otherwise it is cancelled with refunds: two accounts must not split the guarantee in one game.
   */
  GUARANTEED_TOURNAMENT_MIN_PLAYERS: z.coerce.number().int().min(2).max(64).default(4),
  /** Threads where the strong bots think (0: inline, small searches — tests). */
  BRAIN_THREADS: z.coerce.number().int().min(0).max(8).default(3),
  /** Self-play training of the bots in the background: «on» or «off». */
  BOT_TRAINING: z.enum(['on', 'off']).default('off'),
  /** Share of one CPU core the training may use. */
  BOT_TRAINING_DUTY: z.coerce.number().min(0.05).max(0.9).default(0.5),
  CORS_ORIGINS: z.string().default(''),
  /** Directory with the built web app; served from the same origin as the API. */
  WEB_DIST: z.string().default('../web/dist'),
  /** Local development only: lets /auth/dev log in without Telegram. Refused in production. */
  DEV_AUTH: bool,
  /** Bot API base URL; tests point it at a fake. Empty disables bot messages. */
  TELEGRAM_API_URL: z.string().default('https://api.telegram.org'),
  LOG_LEVEL: z.enum(['fatal', 'error', 'warn', 'info', 'debug', 'trace']).default('info'),
});

export type Config = z.infer<typeof schema>;

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  const parsed = schema.safeParse(env);
  if (!parsed.success) {
    const fields = parsed.error.issues.map((i) => i.path.join('.')).join(', ');
    throw new Error(`Invalid environment: ${fields}`);
  }
  if (parsed.data.NODE_ENV === 'production' && parsed.data.DEV_AUTH) {
    throw new Error('DEV_AUTH must not be enabled in production');
  }
  // Without Redis a crash or an update loses every running game: never in production.
  if (parsed.data.NODE_ENV === 'production' && !parsed.data.REDIS_URL) {
    throw new Error('REDIS_URL is required in production');
  }
  return parsed.data;
}
