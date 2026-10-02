import type { AuthResponse } from '@arena/shared';
import type { FastifyInstance } from 'fastify';
import { z } from 'zod';
import { issueSession, readSession } from '../auth/session.js';
import { bearerToken } from '../auth/plugin.js';
import type { Context } from '../context.js';
import { AppError } from '../lib/errors.js';
import { isBanned } from '../services/users.js';
import { signInitData, verifyInitData } from '../telegram/initData.js';

const bodySchema = z.object({ initData: z.string().min(1).max(8192) });
/** How long after expiry a session can still be renewed. */
const REFRESH_GRACE_MS = 7 * 24 * 3600_000;
const devSchema = z.object({ id: z.number().int().positive(), name: z.string().min(1).max(64) });

export async function authRoutes(app: FastifyInstance, ctx: Context): Promise<void> {
  const { config } = ctx;

  const login = async (initData: string): Promise<AuthResponse> => {
    const verified = verifyInitData(initData, config.BOT_TOKEN, config.INIT_DATA_MAX_AGE_SECONDS);
    if (!verified.ok) throw new AppError(verified.error);

    const user = await ctx.users.upsertFromTelegram(verified.data.user);
    if (isBanned(user)) throw new AppError('BANNED');

    const expiresAt = Date.now() + config.SESSION_TTL_HOURS * 3600_000;
    const token = issueSession(
      { sub: user.id, tg: verified.data.user.id, exp: Math.floor(expiresAt / 1000) },
      config.SESSION_SECRET,
    );
    const me = await ctx.users.me(user.id);
    if (!me) throw new AppError('SERVER_ERROR', 500);
    return { token, expiresAt, me, startParam: verified.data.startParam };
  };

  /**
   * A new session for the current one. Telegram's initData is fixed when the Mini App opens and
   * is accepted for an hour only, so a long-open (or long-minimised) app renews its token here.
   */
  app.post('/auth/refresh', { config: { rateLimit: { max: 30, timeWindow: '1 minute' } } }, async (request) => {
    const claims = readSession(bearerToken(request) ?? '', config.SESSION_SECRET, Date.now(), REFRESH_GRACE_MS);
    if (!claims) throw new AppError('UNAUTHORIZED');
    const user = await ctx.db.user.findUnique({ where: { id: claims.sub } });
    if (!user) throw new AppError('UNAUTHORIZED');
    if (isBanned(user)) throw new AppError('BANNED');
    const expiresAt = Date.now() + config.SESSION_TTL_HOURS * 3600_000;
    const token = issueSession({ sub: user.id, tg: claims.tg, exp: Math.floor(expiresAt / 1000) }, config.SESSION_SECRET);
    return { token, expiresAt };
  });

  app.post(
    '/auth/telegram',
    { config: { rateLimit: { max: config.AUTH_RATE_LIMIT, timeWindow: '1 minute' } } },
    async (request) => login(bodySchema.parse(request.body).initData),
  );

  // Local development without Telegram: signs initData with the real bot token, so the
  // exact production verification path still runs. Not registered in production.
  if (config.DEV_AUTH && config.NODE_ENV !== 'production') {
    app.post('/auth/dev', async (request) => {
      const body = devSchema.parse(request.body);
      const initData = signInitData(
        {
          auth_date: String(Math.floor(Date.now() / 1000)),
          user: JSON.stringify({ id: body.id, first_name: body.name, language_code: 'ru' }),
        },
        config.BOT_TOKEN,
      );
      return login(initData);
    });
  }
}
