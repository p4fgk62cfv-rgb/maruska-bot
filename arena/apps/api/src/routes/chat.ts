import type { ChatMessageDto, ChatStateDto } from '@arena/shared';
import { CHAT } from '@arena/shared';
import type { FastifyInstance } from 'fastify';
import { z } from 'zod';
import { requireSession, sessionOf } from '../auth/plugin.js';
import type { Context } from '../context.js';

const idParam = z.object({ id: z.uuid() });

/** «Общий чат»: history, writing, reports; owners delete and mute. */
export async function chatRoutes(app: FastifyInstance, ctx: Context): Promise<void> {
  const auth = { preHandler: requireSession(ctx.config.SESSION_SECRET) };

  app.get('/chat', auth, async (request): Promise<ChatStateDto> => {
    const { before } = z.object({ before: z.uuid().optional() }).parse(request.query);
    return ctx.chat.state(sessionOf(request).sub, before);
  });

  app.post('/chat', { ...auth, config: { rateLimit: { max: 20, timeWindow: '1 minute' } } }, async (request): Promise<ChatMessageDto> => {
    const { text } = z.object({ text: z.string().min(1).max(CHAT.maxLength * 2) }).parse(request.body);
    return ctx.chat.send(sessionOf(request).sub, text);
  });

  app.post('/chat/:id/report', { ...auth, config: { rateLimit: { max: 20, timeWindow: '1 minute' } } }, async (request) => {
    await ctx.chat.report(sessionOf(request).sub, idParam.parse(request.params).id);
    return { ok: true };
  });

  app.delete('/chat/:id', auth, async (request) => {
    await ctx.chat.remove(sessionOf(request).sub, idParam.parse(request.params).id);
    return { ok: true };
  });

  app.post('/chat/mute', auth, async (request) => {
    const body = z.object({ userId: z.uuid(), hours: z.number().int().min(0).max(24 * 365), purge: z.boolean().default(false) }).parse(request.body);
    return { until: await ctx.chat.mute(sessionOf(request).sub, body.userId, body.hours, body.purge) };
  });
}
