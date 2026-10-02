import { buildApp } from './app.js';
import { loadConfig } from './config.js';
import { createContext } from './context.js';
import { createDb } from './db.js';
import { seedCatalog } from './services/catalog.js';
import { MemoryStore, RedisStore } from './realtime/store.js';

async function main(): Promise<void> {
  const config = loadConfig();
  const db = createDb(config.DATABASE_URL, config.DB_POOL_SIZE);
  await seedCatalog(db);

  // Without Redis live games cannot survive a restart: they are refunded on the next boot.
  const store = config.REDIS_URL ? new RedisStore(config.REDIS_URL) : new MemoryStore();
  const { app, ctx } = await buildApp(createContext(config, db), { store, background: true });
  if (!config.REDIS_URL) app.log.warn('REDIS_URL is not set: running games will be refunded after a restart');

  const shutdown = async (signal: string) => {
    app.log.info({ signal }, 'shutting down');
    // Before the sockets close: tell everyone, cancel the running games with stakes returned.
    await ctx.realtime.stopForRestart().catch((error: unknown) => app.log.error({ err: error }, 'restart notice failed'));
    await app.close();
    await db.$disconnect();
    process.exit(0);
  };
  process.on('SIGTERM', () => void shutdown('SIGTERM'));
  process.on('SIGINT', () => void shutdown('SIGINT'));

  await app.listen({ host: '0.0.0.0', port: config.PORT });
}

main().catch((error: unknown) => {
  console.error(error);
  process.exit(1);
});
