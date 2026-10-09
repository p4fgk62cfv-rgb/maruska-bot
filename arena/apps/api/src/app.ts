import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import cors from '@fastify/cors';
import rateLimit from '@fastify/rate-limit';
import fastifyStatic from '@fastify/static';
import { errorText, type ApiErrorBody } from '@arena/shared';
import Fastify, { type FastifyInstance } from 'fastify';
import { ZodError } from 'zod';
import { ownerIds, type BaseContext, type Context } from './context.js';
import { bearerToken, useBanList } from './auth/plugin.js';
import { AppError } from './lib/errors.js';
import { requestSerializer, securityHeaders } from './lib/security.js';
import { authRoutes } from './routes/auth.js';
import { boardRoutes } from './routes/board.js';
import { profileRoutes } from './routes/profile.js';
import { roomRoutes } from './routes/rooms.js';
import { Realtime } from './realtime/realtime.js';
import { MemoryStore, ResilientStore, type SnapshotStore } from './realtime/store.js';
import { Alerts } from './services/alerts.js';
import { websocketRoutes } from './realtime/ws.js';
import { RealtimePresence } from './services/presence.js';
import { FriendService } from './services/friends.js';
import { ProfileService } from './services/profiles.js';
import { ReferralService } from './services/referrals.js';
import { referralRoutes } from './routes/referrals.js';
import { dailyRoutes } from './routes/daily.js';
import { chatRoutes } from './routes/chat.js';
import { ChatService } from './services/chat.js';
import { Brain } from './brain/brain.js';
import { Trainer } from './brain/trainer.js';
import { Showcase } from './brain/showcase.js';
import { Outbox, TelegramBot } from './services/notifier.js';
import { playerRoutes } from './routes/players.js';
import { ownerRoutes } from './routes/owner.js';
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
  /** Take over the games in the background (production: the old server may still hold them). */
  background?: boolean;
  /** Replaces the owner alerts (tests). */
  alerts?: Alerts;
  /** Where logs go (tests capture them to check nothing secret is written). */
  logStream?: { write(line: string): void };
}

export async function buildApp(base: BaseContext, options: AppOptions = {}): Promise<AppHandle> {
  const { config } = base;
  const app = Fastify({
    logger:
      config.NODE_ENV === 'test' && !options.logStream
        ? false
        : {
            level: config.LOG_LEVEL,
            serializers: { req: requestSerializer },
            redact: ['req.headers.authorization', 'headers.authorization'],
            ...(options.logStream ? { stream: options.logStream } : {}),
          },
    trustProxy: true,
    bodyLimit: 64 * 1024,
  });

  app.decorateRequest('session', null);
  securityHeaders(app);

  const bot = options.bot !== undefined ? options.bot : config.TELEGRAM_API_URL ? new TelegramBot(config.BOT_TOKEN, config.TELEGRAM_API_URL) : null;
  const alerts = options.alerts ?? new Alerts(bot, ownerIds(config.OWNER_IDS), app.log);
  // A failed snapshot write is retried until it lands; the games never wait for it.
  const store = new ResilientStore(options.store ?? new MemoryStore(), app.log, alerts);
  const brain = new Brain(base.db, app.log, config.NODE_ENV === 'test' ? 0 : config.BRAIN_THREADS);
  await brain.start();
  const trainer = new Trainer(base.db, brain, app.log, { duty: config.BOT_TRAINING_DUTY });
  const realtime = new Realtime({ ...base, store, log: app.log, alerts, brain });
  const showcase = new Showcase({
    publish: (message) => realtime.hub.publishTraining(message),
    watched: () => realtime.hub.hasTrainingWatchers(),
    players: () => trainer.current,
    fallback: () => ({ params: brain.params, version: brain.version }),
  });
  realtime.trainingTables = () => showcase.snapshot();
  const presence = new RealtimePresence(realtime);
  const outbox = new Outbox(base.db, bot, app.log);
  const friends = new FriendService({ ...base, outbox, presence, realtime });
  const tournaments = new TournamentService({ ...base, outbox, realtime, log: app.log });
  const profiles = new ProfileService({ db: base.db, items: base.items, presence, friends: () => friends });
  const referrals = new ReferralService({ ...base, outbox, realtime, log: app.log });
  realtime.finishedListeners.add((result) => {
    referrals.onGame(result).catch((error: unknown) => app.log.error({ err: error }, 'referral reward failed'));
  });
  const chat = new ChatService({
    db: base.db,
    publish: (message) => realtime.hub.publishChat(message),
    online: () => realtime.hub.onlineUsers().length,
    owners: ownerIds(config.OWNER_IDS),
    outbox,
    log: app.log,
  });
  base.users.useChat(chat);
  const ctx: Context = { ...base, realtime, presence, outbox, friends, profiles, tournaments, referrals, alerts, chat, brain, trainer };
  await base.moderation.loadBans();
  useBanList(base.moderation);
  await base.bots.ensurePool();
  await base.bots.settings();
  // During a deploy the previous server hands the games over only when it stops, which can be
  // after this one starts listening: in production the take-over runs in the background and
  // requests that touch tables wait for it (see the hook below).
  if (options.background) realtime.start().catch((error: unknown) => alerts.raise('takeover', 'Сервер не смог принять столы после запуска', { err: error }));
  else await realtime.start();
  if (config.NODE_ENV !== 'test') {
    outbox.start();
    chat.start();
    void realtime.ready.then(() => tournaments.start());
    // One server trains: the one that runs the games (it holds the lease).
    if (config.BOT_TRAINING === 'on') {
      void realtime.ready
        .then(() => trainer.start())
        .then((on) => {
          if (on) app.log.info('bot training started');
          showcase.start();
        })
        .catch((err: unknown) => app.log.error({ err }, 'bot training did not start'));
    }
  }
  app.addHook('onRequest', async (request) => {
    if (request.url.startsWith('/api/rooms') || request.url.startsWith('/api/friends') || request.url.startsWith('/api/tournaments')) await realtime.ready;
  });
  app.addHook('onClose', async () => {
    outbox.stop();
    chat.stop();
    tournaments.stop();
    showcase.stop();
    await trainer.stop();
    await realtime.shutdown();
    await brain.stop();
  });

  const origins = config.CORS_ORIGINS.split(',').map((o) => o.trim()).filter(Boolean);
  if (origins.length) await app.register(cors, { origin: origins });

  await app.register(rateLimit, {
    max: 300,
    timeWindow: '1 minute',
    // Mobile carriers put many players behind one IP, so signed-in requests are limited per session.
    // /ws carries the session in the query string (WebViews cannot set socket headers).
    keyGenerator: (request) => bearerToken(request) ?? (request.query as { token?: string } | undefined)?.token ?? request.ip,
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

  /** Railway health check: the process can serve players (database and snapshot store reachable). */
  app.get('/ready', async (_request, reply) => {
    try {
      await base.db.$queryRaw`SELECT 1`;
      await store.ping();
      return { ok: true };
    } catch {
      return reply.status(503).send({ ok: false });
    }
  });

  app.get('/health', async () => ({ ok: true, service: 'arena', games: realtime.games.count(), online: realtime.hub.onlineUsers().length, unsaved: realtime.storeBacklog() }));
  await websocketRoutes(app, ctx);

  await app.register(
    async (api) => {
      await authRoutes(api, ctx);
      await profileRoutes(api, ctx);
      await boardRoutes(api, ctx);
      await roomRoutes(api, ctx);
      await friendRoutes(api, ctx);
      await playerRoutes(api, ctx);
      await referralRoutes(api, ctx);
      await dailyRoutes(api, ctx);
      await chatRoutes(api, ctx);
      await ownerRoutes(api, ctx);
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
      // dist carries .br/.gz copies made at build time (apps/web/scripts/compress.mjs).
      preCompressed: true,
      // Our own Cache-Control below; otherwise the plugin overwrites it with «max-age=0».
      cacheControl: false,
      setHeaders: (res, path) => {
        // Hashed bundles are immutable; index.html must always be fresh. Card faces, backs, the
        // table, smiles and sounds keep for a week (re-checked after that), so a card moving from
        // the hand to the table never waits for the network and never shows up blank.
        res.header(
          'Cache-Control',
          path.includes('/assets/')
            ? 'public, max-age=31536000, immutable'
            : /\/(cards|backs|table|emoji|sfx)\//.test(path)
              ? 'public, max-age=604800, stale-while-revalidate=86400'
              : 'no-cache',
        );
      },
    });
    app.setNotFoundHandler((request, reply) => {
      if (request.method === 'GET' && !request.url.startsWith('/api')) return reply.sendFile('index.html');
      return reply.status(404).send({ error: 'NOT_FOUND', message: errorText('NOT_FOUND') });
    });
  }

  return { app, ctx };
}
