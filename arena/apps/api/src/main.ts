import { buildApp } from './app.js';
import { loadConfig } from './config.js';
import { createContext } from './context.js';
import { createDb } from './db.js';
import { seedCatalog } from './services/catalog.js';
import { MemoryStore, RedisStore } from './realtime/store.js';

/** The event loop stuck this long (a hot loop, a huge sync job) is reported to the owners. */
const STALL_MS = 2_000;

async function main(): Promise<void> {
  const config = loadConfig();
  const db = createDb(config.DATABASE_URL, config.DB_POOL_SIZE);
  await seedCatalog(db);

  // Without Redis live games cannot survive a restart (production refuses to start without it).
  const store = config.REDIS_URL ? new RedisStore(config.REDIS_URL) : new MemoryStore();
  const { app, ctx } = await buildApp(createContext(config, db), { store, background: true });
  if (!config.REDIS_URL) app.log.warn('REDIS_URL is not set: running games will be refunded after a restart');

  let stopping: Promise<void> | null = null;
  const shutdown = (signal: string, code = 0) => {
    stopping ??= (async () => {
      app.log.info({ signal }, 'shutting down');
      // Never hang on the way out (Railway allows 20 s to drain, then kills).
      setTimeout(() => process.exit(code || 1), 18_000).unref();
      // Before the sockets close: tell everyone, cancel the running games with stakes returned.
      await ctx.realtime.stopForRestart().catch((error: unknown) => app.log.error({ err: error }, 'restart notice failed'));
      await app.close().catch((error: unknown) => app.log.error({ err: error }, 'close failed'));
      await db.$disconnect().catch(() => undefined);
      process.exit(code);
    })();
    return stopping;
  };
  process.on('SIGTERM', () => void shutdown('SIGTERM'));
  process.on('SIGINT', () => void shutdown('SIGINT'));

  // A forgotten promise must not take every table down with it: report and keep serving.
  process.on('unhandledRejection', (reason) => {
    ctx.alerts.raise('unhandled', 'Необработанная ошибка на сервере (сервер продолжает работу).', { err: reason });
  });
  // After a thrown exception the process state is unknown: hand the tables over cleanly
  // (stakes back, tournament games saved) and let the platform start a fresh one.
  process.on('uncaughtException', (error) => {
    ctx.alerts.raise('crash', 'Критическая ошибка: сервер перезапускается, ставки текущих игр возвращаются.', { err: error });
    void shutdown('uncaughtException', 1);
  });

  let last = Date.now();
  setInterval(() => {
    const now = Date.now();
    const stalled = now - last - 1000;
    last = now;
    if (stalled >= STALL_MS) ctx.alerts.raise('stall', `Сервер завис на ${(stalled / 1000).toFixed(1)} с — игроки видели задержку.`);
  }, 1000).unref();

  await app.listen({ host: '0.0.0.0', port: config.PORT });
}

main().catch((error: unknown) => {
  console.error(error);
  process.exit(1);
});
