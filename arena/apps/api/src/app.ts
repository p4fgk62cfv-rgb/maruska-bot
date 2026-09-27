import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import cors from '@fastify/cors';
import rateLimit from '@fastify/rate-limit';
import fastifyStatic from '@fastify/static';
import { errorText, type ApiErrorBody } from '@arena/shared';
import Fastify, { type FastifyInstance } from 'fastify';
import { ZodError } from 'zod';
import type { Context } from './context.js';
import { bearerToken } from './auth/plugin.js';
import { AppError } from './lib/errors.js';
import { authRoutes } from './routes/auth.js';
import { boardRoutes } from './routes/board.js';
import { profileRoutes } from './routes/profile.js';

export async function buildApp(ctx: Context): Promise<FastifyInstance> {
  const { config } = ctx;
  const app = Fastify({
    logger: config.NODE_ENV === 'test' ? false : { level: config.LOG_LEVEL, redact: ['req.headers.authorization'] },
    trustProxy: true,
    bodyLimit: 64 * 1024,
  });

  app.decorateRequest('session', null);

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

  app.get('/health', async () => ({ ok: true, service: 'arena' }));

  await app.register(
    async (api) => {
      await authRoutes(api, ctx);
      await profileRoutes(api, ctx);
      await boardRoutes(api, ctx);
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

  return app;
}
