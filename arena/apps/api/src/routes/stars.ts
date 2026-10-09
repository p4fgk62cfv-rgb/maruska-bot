import type { OwnerStarsDto, StarOrderDto, StarPack } from '@arena/shared';
import type { FastifyInstance, FastifyRequest } from 'fastify';
import { z } from 'zod';
import { requireSession, sessionOf } from '../auth/plugin.js';
import type { Context } from '../context.js';
import { AppError } from '../lib/errors.js';

const idParam = z.object({ id: z.uuid() });

/** «Монеты за звёзды»: packs, invoice links and the order status; the owner's list and refunds. */
export async function starsRoutes(app: FastifyInstance, ctx: Context): Promise<void> {
  const auth = { preHandler: requireSession(ctx.config.SESSION_SECRET) };
  const buy = { ...auth, config: { rateLimit: { max: 10, timeWindow: '1 minute' } } };

  app.get('/stars/packs', auth, async (): Promise<{ enabled: boolean; packs: readonly StarPack[] }> => ctx.stars.packs());

  app.post('/stars/orders', buy, async (request): Promise<{ order: StarOrderDto; link: string }> => {
    const { pack } = z.object({ pack: z.string().max(32) }).parse(request.body);
    return ctx.stars.createOrder(sessionOf(request).sub, pack);
  });

  app.get('/stars/orders/:id', auth, async (request): Promise<StarOrderDto> => {
    const { id } = idParam.parse(request.params);
    return ctx.stars.order(sessionOf(request).sub, id);
  });

  const owner = async (request: FastifyRequest) => {
    const user = await ctx.db.user.findUnique({ where: { id: sessionOf(request).sub }, select: { telegramId: true } });
    if (!user || !ctx.users.isOwnerTelegram(user.telegramId)) throw new AppError('FORBIDDEN');
  };

  app.get('/owner/stars', auth, async (request): Promise<OwnerStarsDto> => {
    await owner(request);
    return ctx.stars.ownerList();
  });

  app.post('/owner/stars/:id/refund', auth, async (request): Promise<StarOrderDto> => {
    await owner(request);
    const { id } = idParam.parse(request.params);
    return ctx.stars.refund(id);
  });
}
