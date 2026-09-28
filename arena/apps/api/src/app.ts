import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import cors from '@fastify/cors';
import rateLimit from '@fastify/rate-limit';
import fastifyStatic from '@fastify/static';
import { errorText, type ApiErrorBody } from '@arena/shared';
import Fastify, { type FastifyInstance } from 'fastify';
import { ZodError } from 'zod';
import type { BaseContext, Context } from './context.js';
import { bearerToken } from './auth/plugin.js';
import { AppError } from './lib/errors.js';
import { authRoutes } from './routes/auth.js';
import { boardRoutes } from './routes/board.js';
import { profileRoutes } from './routes/profile.js';
import { roomRoutes } from './routes/rooms.js';
import { Realtime } from './realtime/realtime.js';
import { MemoryStore, type SnapshotStore } from './realtime/store.js';
import { websocketRoutes } from './realtime/ws.js';
import { RealtimePresence } from './services/presence.js';
import { FriendService } from './services/friends.js';
import { Outbox, TelegramBot } from './services/notifier.js';
import { friendRoutes } from './routes/friends.js';
import { internalRoutes } from './routes/internal.js';
import { tournamentRoutes } from './routes/tournaments.js';
import { TournamentService } from './services/tournaments.js';

export interface AppHandle {
  app: FastifyInstance;
  ctx: Context;
}

export interface AppOptions {
  store?: SnapshotStore;
  /** Replaces the Telegram HTTP client (tests). */
  bot?: TelegramBot | null;
}

export async function buildApp(base: BaseContext, options: AppOptions = {}): Promise<AppHandle> {
  const store = options.store ?? new MemoryStore();
  const { config } = base;
  const app = Fastify({
    logger: config.NODE_ENV === 'test' ? false : { level: config.LOG_LEVEL, redact: ['req.headers.authorization'] },
    trustProxy: true,
    bodyLimit: 64 * 1024,
  });

  app.decorateRequest('session', null);

  const realtime = new Realtime({ ...base, store, log: app.log });
  const presence = new RealtimePresence(realtime);
  const bot = options.bot !== undefined ? options.bot : config.TELEGRAM_API_URL ? new TelegramBot(config.BOT_TOKEN, config.TELEGRAM_API_URL) : null;
  const outbox = new Outbox(base.db, bot, app.log);
  const friends = new FriendService({ ...base, outbox, presence, realtime });
  const tournaments = new TournamentService({ ...base, outbox, realtime, log: app.log });
  const ctx: Context = { ...base, realtime, presence, outbox, friends, tournaments };
  await realtime.recover();
  if (config.NODE_ENV !== 'test') {
    outbox.start();
    tournaments.start();
  }
  app.addHook('onClose', async () => {
    outbox.stop();
    tournaments.stop();
    await realtime.shutdown();
  });

  const origins = config.CORS_ORIGINS.split(',').map((o) => o.trim()).filter(Boolean);
  if (origins.length) await app.register(cors, { origin: origins });

  await app.register(rateLimit, {
    max: 300,
    timeWindow: '1 minute',
    // Mobile carriers put many players behind one IP, so signed-in requests are limited per session.
    keyGenerator: (request) => bearerToken(request) ?? request.ip,
    errorResponseBuilder: (): ApiErrorBody & { statusCode: number } => ({
      statusCode: 429,
      error: 'RATE_LIMITED',
      message: errorText('RATE_LIMITED'),
    }),
  });

  app.setErrorHandler((error, request, reply) => {
    if (error instanceof AppError) {
      return reply.status(error.status).send({ error: error.code, message: error.message } satisfies ApiErrorBody);
    }
    if (error instanceof ZodError) {
      return reply.status(400).send({ error: 'VALIDATION_FAILED', message: errorText('VALIDATION_FAILED') });
    }
    const status = (error as { statusCode?: number }).statusCode;
    if (status === 429) return reply.status(429).send(error);
    if (status && status >= 400 && status < 500) {
      return reply.status(status).send({ error: 'VALIDATION_FAILED', message: errorText('VALIDATION_FAILED') });
    }
    request.log.error({ err: error }, 'unhandled error');
    return reply.status(500).send({ error: 'SERVER_ERROR', message: errorText('SERVER_ERROR') });
  });

  app.get('/health', async () => ({ ok: true, service: 'arena', games: realtime.games.count(), online: realtime.hub.onlineUsers().length }));
  await websocketRoutes(app, ctx);

  await app.register(
    async (api) => {
      await authRoutes(api, ctx);
      await profileRoutes(api, ctx);
      await boardRoutes(api, ctx);
      await roomRoutes(api, ctx);
      await friendRoutes(api, ctx);
      await tournamentRoutes(api, ctx);
      await internalRoutes(api, ctx);
    },
    { prefix: '/api' },
  );

  const webDist = resolve(process.cwd(), config.WEB_DIST);
  if (existsSync(webDist)) {
    await app.register(fastifyStatic, {
      root: webDist,
      wildcard: false,
      setHeaders: (res, path) => {
        // Hashed bundles are immutable; index.html must always be fresh.
        res.setHeader('Cache-Control', path.includes('/assets/') ? 'public, max-age=31536000, immutable' : 'no-cache');
      },
    });
    app.setNotFoundHandler((request, reply) => {
      if (request.method === 'GET' && !request.url.startsWith('/api')) return reply.sendFile('index.html');
      return reply.status(404).send({ error: 'NOT_FOUND', message: errorText('NOT_FOUND') });
    });
  }

  return { app, ctx };
}
