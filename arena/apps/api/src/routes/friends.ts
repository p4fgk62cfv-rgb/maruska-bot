import type { FastifyInstance } from 'fastify';
import { z } from 'zod';
import { requireSession, sessionOf } from '../auth/plugin.js';
import type { Context } from '../context.js';

const userParam = z.object({ userId: z.uuid() });
const requestParam = z.object({ id: z.uuid() });

export async function friendRoutes(app: FastifyInstance, ctx: Context): Promise<void> {
  const auth = { preHandler: requireSession(ctx.config.SESSION_SECRET) };
  const friends = ctx.friends;
  const me = (request: Parameters<typeof sessionOf>[0]) => sessionOf(request).sub;

  app.get('/friends', auth, async (request) => friends.list(me(request)));
  app.get('/friends/of-friends', auth, async (request) => friends.friendsOfFriends(me(request)));
  app.get('/friends/requests', auth, async (request) => friends.requests(me(request)));
  app.get('/friends/recent', auth, async (request) => friends.recent(me(request)));

  app.post('/friends/requests', { ...auth, config: { rateLimit: { max: 30, timeWindow: '1 minute' } } }, async (request) => {
    const { userId } = userParam.parse(request.body);
    return friends.send(me(request), userId);
  });
  app.post('/friends/requests/:id/accept', auth, async (request) => {
    await friends.accept(me(request), requestParam.parse(request.params).id);
    return { ok: true };
  });
  app.post('/friends/requests/:id/decline', auth, async (request) => {
    await friends.decline(me(request), requestParam.parse(request.params).id);
    return { ok: true };
  });
  app.delete('/friends/requests/:id', auth, async (request) => {
    await friends.cancel(me(request), requestParam.parse(request.params).id);
    return { ok: true };
  });
  app.delete('/friends/:userId', auth, async (request) => {
    await friends.remove(me(request), userParam.parse(request.params).userId);
    return { ok: true };
  });
  app.post('/friends/:userId/invite', auth, async (request) => {
    await friends.invite(me(request), userParam.parse(request.params).userId);
    return { ok: true };
  });
  app.get('/users/search', auth, async (request) => {
    const { q } = z.object({ q: z.string().max(40).default('') }).parse(request.query);
    return friends.search(me(request), q);
  });
}
