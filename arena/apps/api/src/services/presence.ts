import type { FriendDto } from '@arena/shared';

/**
 * Who is online and where. Stage 1 keeps it in memory for a single instance;
 * stage 2 swaps in the Redis implementation so every instance sees the same picture.
 */
export interface Presence {
  onlineByServer(): Promise<Record<string, number>>;
  lookup(userIds: string[]): Promise<Record<string, FriendDto['presence']>>;
}

export class MemoryPresence implements Presence {
  private readonly users = new Map<string, { server: string | null; inGame: boolean }>();

  set(userId: string, server: string | null, inGame: boolean): void {
    this.users.set(userId, { server, inGame });
  }

  remove(userId: string): void {
    this.users.delete(userId);
  }

  async onlineByServer(): Promise<Record<string, number>> {
    const counts: Record<string, number> = {};
    for (const { server } of this.users.values()) if (server) counts[server] = (counts[server] ?? 0) + 1;
    return counts;
  }

  async lookup(userIds: string[]): Promise<Record<string, FriendDto['presence']>> {
    const result: Record<string, FriendDto['presence']> = {};
    for (const id of userIds) {
      const entry = this.users.get(id);
      result[id] = entry ? (entry.inGame ? 'in_game' : 'online') : 'offline';
    }
    return result;
  }
}
