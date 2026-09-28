import { PrismaPg } from '@prisma/adapter-pg';
import { PrismaClient } from './generated/prisma/client.js';

export type Db = PrismaClient;

/** `?schema=` is for Prisma Migrate; every model already names its schema explicitly. */
function connectionString(url: string): string {
  const parsed = new URL(url);
  parsed.searchParams.delete('schema');
  return parsed.toString();
}

/**
 * Bursts of game starts and settlements queue for a pooled connection, so transactions wait
 * longer than Prisma's 2 s default before giving up.
 */
export function createDb(url: string, poolSize = 20): Db {
  const adapter = new PrismaPg({ connectionString: connectionString(url), max: poolSize });
  return new PrismaClient({ adapter, transactionOptions: { maxWait: 10_000, timeout: 15_000 } });
}
