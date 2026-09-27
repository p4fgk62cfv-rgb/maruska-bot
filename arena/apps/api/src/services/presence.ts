import type { FriendDto } from '@arena/shared';
import type { Realtime } from '../realtime/realtime.js';

/** Who is online and where, as seen by this game server. */
export interface Presence {
  onlineByServer(): Promise<Record<string, number>>;
  lookup(userIds: string[]): Promise<Record<string, FriendDto['presence']>>;
}

export class RealtimePresence implements Presence {
  constructor(private readonly realtime: Realtime) {}

  async onlineByServer(): Promise<Record<string, number>> {
    return this.realtime.rooms.onlineByServer();
  }

  async lookup(userIds: string[]): Promise<Record<string, FriendDto['presence']>> {
    const result: Record<string, FriendDto['presence']> = {};
    for (const id of userIds) {
      if (this.realtime.games.forUser(id)) result[id] = 'in_game';
      else result[id] = this.realtime.hub.isOnline(id) ? 'online' : 'offline';
    }
    return result;
  }
}
