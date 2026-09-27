import { PrismaPg } from '@prisma/adapter-pg';
import { PrismaClient } from './generated/prisma/client.js';

export type Db = PrismaClient;

/** `?schema=` is for Prisma Migrate; every model already names its schema explicitly. */
function connectionString(url: string): string {
  const parsed = new URL(url);
  parsed.searchParams.delete('schema');
  return parsed.toString();
}

export function createDb(url: string): Db {
  const adapter = new PrismaPg({ connectionString: connectionString(url), max: 10 });
  return new PrismaClient({ adapter });
}
