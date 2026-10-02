import type { ReferralInfoDto } from '@arena/shared';
import type { FastifyInstance } from 'fastify';
import { requireSession, sessionOf } from '../auth/plugin.js';
import type { Context } from '../context.js';

/** «Пригласить друга»: my link, the reward and whom I brought. */
export async function referralRoutes(app: FastifyInstance, ctx: Context): Promise<void> {
  const auth = { preHandler: requireSession(ctx.config.SESSION_SECRET) };

  app.get('/referrals', auth, async (request): Promise<ReferralInfoDto> => ctx.referrals.info(sessionOf(request).sub));
}
