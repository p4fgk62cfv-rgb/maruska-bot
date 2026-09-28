import type { FastifyInstance } from 'fastify';
import { z } from 'zod';
import { requireSession, sessionOf } from '../auth/plugin.js';
import type { Context } from '../context.js';

export async function tournamentRoutes(app: FastifyInstance, ctx: Context): Promise<void> {
  const auth = { preHandler: requireSession(ctx.config.SESSION_SECRET) };
  const idParam = z.object({ id: z.uuid() });

  app.get('/tournaments', auth, async (request) => {
    const { status } = z.object({ status: z.enum(['active', 'finished']).default('active') }).parse(request.query);
    return ctx.tournaments.list(sessionOf(request).sub, status === 'active');
  });
  app.get('/tournaments/:id', auth, async (request) => ctx.tournaments.detail(sessionOf(request).sub, idParam.parse(request.params).id));
  app.post('/tournaments/:id/register', auth, async (request) => {
    const { id } = idParam.parse(request.params);
    await ctx.tournaments.register(sessionOf(request).sub, id);
    return ctx.tournaments.detail(sessionOf(request).sub, id);
  });
  app.post('/tournaments/:id/unregister', auth, async (request) => {
    const { id } = idParam.parse(request.params);
    await ctx.tournaments.unregister(sessionOf(request).sub, id);
    return ctx.tournaments.detail(sessionOf(request).sub, id);
  });
}
