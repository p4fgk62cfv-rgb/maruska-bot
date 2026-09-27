import { buildApp } from './app.js';
import { loadConfig } from './config.js';
import { createContext } from './context.js';
import { createDb } from './db.js';
import { seedCatalog } from './services/catalog.js';

async function main(): Promise<void> {
  const config = loadConfig();
  const db = createDb(config.DATABASE_URL);
  await seedCatalog(db);

  const app = await buildApp(createContext(config, db));

  const shutdown = async (signal: string) => {
    app.log.info({ signal }, 'shutting down');
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
