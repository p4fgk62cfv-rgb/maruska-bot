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
  /** Signs session tokens. At least 32 random characters. */
  SESSION_SECRET: z.string().min(32),
  SESSION_TTL_HOURS: z.coerce.number().int().positive().default(24),
  /** How old a Telegram initData may be when exchanged for a session. */
  INIT_DATA_MAX_AGE_SECONDS: z.coerce.number().int().positive().default(3600),
  /** Shared secret for bot → arena calls on /internal/*. */
  INTERNAL_API_SECRET: z.string().min(16).optional(),
  SIGNUP_BONUS_CREDITS: z.coerce.number().int().nonnegative().default(1_450),
  RAKE_PERCENT: z.coerce.number().min(0).max(50).default(5),
  CORS_ORIGINS: z.string().default(''),
  /** Directory with the built web app; served from the same origin as the API. */
  WEB_DIST: z.string().default('../web/dist'),
  /** Local development only: lets /auth/dev log in without Telegram. Refused in production. */
  DEV_AUTH: bool,
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
  return parsed.data;
}
