import type { MyRoomDto, RoomDto } from '@arena/shared';
import { joinRoomSchema, quickGameSchema, roomFilterSchema, roomSettingsSchema } from '@arena/shared/schemas';
import { matchesFilter } from '@arena/shared';
import type { FastifyInstance } from 'fastify';
import { z } from 'zod';
import { requireSession, sessionOf } from '../auth/plugin.js';
import type { Context } from '../context.js';
import { AppError } from '../lib/errors.js';
import { isListed } from '../realtime/hub.js';

const idParam = z.object({ id: z.string().regex(/^[A-Z0-9]{8}$/) });
const csv = (schema: z.ZodType) => z.preprocess((v) => (typeof v === 'string' && v ? v.split(',') : []), z.array(schema));

const listQuery = z.object({
  stakes: csv(z.coerce.number().int()),
  players: csv(z.coerce.number().int()),
  deckSizes: csv(z.coerce.number().int()),
  speeds: csv(z.enum(['normal', 'fast'])),
  modes: csv(z.enum(['podkidnoy', 'perevodnoy', 'all', 'neighbors', 'fair', 'cheaters', 'classic', 'draw'])),
  server: z.string().optional(),
});

export async function roomRoutes(app: FastifyInstance, ctx: Context): Promise<void> {
  const auth = { preHandler: requireSession(ctx.config.SESSION_SECRET) };
  const rooms = () => ctx.realtime.rooms;

  app.get('/rooms', auth, async (request): Promise<RoomDto[]> => {
    const filter = roomFilterSchema.parse(listQuery.parse(request.query));
    return rooms()
      .list()
      .filter((r) => isListed(r) && matchesFilter(r, filter));
  });

  app.post('/rooms', auth, async (request): Promise<MyRoomDto> => {
    return rooms().create(sessionOf(request).sub, roomSettingsSchema.parse(request.body));
  });

  app.post('/rooms/quick', auth, async (request): Promise<MyRoomDto> => {
    const { stake } = quickGameSchema.parse(request.body ?? {});
    return rooms().quick(sessionOf(request).sub, stake);
  });

  /** Public card of a room for deep links: enough to show «Войти» / «Нужен пароль». */
  app.get('/rooms/:id', auth, async (request): Promise<RoomDto & { member: boolean }> => {
    const { id } = idParam.parse(request.params);
    const room = rooms().get(id);
    if (!room) throw new AppError('ROOM_CLOSED');
    return { ...rooms().dto(room), member: room.seats.some((s) => s.userId === sessionOf(request).sub) };
  });

  // Tight limit: private-room passwords must not be guessable by brute force.
  app.post('/rooms/:id/join', { ...auth, config: { rateLimit: { max: 20, timeWindow: '1 minute' } } }, async (request): Promise<MyRoomDto> => {
    const { id } = idParam.parse(request.params);
    return rooms().join(sessionOf(request).sub, id, joinRoomSchema.parse(request.body ?? {}));
  });

  app.post('/rooms/:id/leave', auth, async (request) => {
    const { id } = idParam.parse(request.params);
    await rooms().leave(sessionOf(request).sub, id);
    return { ok: true };
  });

  /** Where am I? Lets the app resume a room or game after being closed. */
  app.get('/me/active', auth, async (request): Promise<MyRoomDto | null> => {
    const room = rooms().roomOf(sessionOf(request).sub);
    return room ? rooms().mine(room) : null;
  });

  app.get('/games/:id', auth, async (request) => {
    const { id } = z.object({ id: z.uuid() }).parse(request.params);
    const game = await ctx.db.game.findUnique({
      where: { id },
      include: { result: true, players: { include: { user: true } } },
    });
    if (!game || !game.players.some((p) => p.userId === sessionOf(request).sub)) throw new AppError('NOT_FOUND');
    return {
      id: game.id,
      status: game.status,
      stake: Number(game.stake),
      startedAt: game.startedAt.toISOString(),
      finishedAt: game.finishedAt?.toISOString() ?? null,
      result: game.result ? { kind: game.result.kind, reason: game.result.reason, winnerId: game.result.winnerId, loserId: game.result.loserId } : null,
      players: game.players.map((p) => ({
        userId: p.userId,
        name: p.user.firstName,
        seat: p.seat,
        place: p.place,
        outcome: p.outcome,
        net: p.net === null ? null : Number(p.net),
        ratingGain: p.ratingGain,
      })),
    };
  });
}
