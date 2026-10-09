import type { DailyDto } from '@arena/shared';
import type { FastifyInstance } from 'fastify';
import { z } from 'zod';
import { requireSession, sessionOf } from '../auth/plugin.js';
import type { Context } from '../context.js';
import { QUEST_KEYS } from '../services/daily.js';

const claimSchema = z.object({
  day: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  key: z.string().refine((key) => QUEST_KEYS.has(key)),
});

/** «Задания»: three quests a day and the login calendar. */
export async function dailyRoutes(app: FastifyInstance, ctx: Context): Promise<void> {
  const auth = { preHandler: requireSession(ctx.config.SESSION_SECRET) };
  const claim = { ...auth, config: { rateLimit: { max: 20, timeWindow: '1 minute' } } };

  app.get('/daily', auth, async (request): Promise<DailyDto> => ctx.daily.get(sessionOf(request).sub));
  app.post('/daily/login', claim, async (request): Promise<DailyDto> => ctx.daily.claimLogin(sessionOf(request).sub));
  app.post('/daily/quests', claim, async (request): Promise<DailyDto> => {
    const { day, key } = claimSchema.parse(request.body);
    return ctx.daily.claimQuest(sessionOf(request).sub, day, key);
  });
}
