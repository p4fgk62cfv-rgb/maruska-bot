import type { RoomDto, RoomFilter, ServerMessage } from '@arena/shared';
import { EMPTY_FILTER, matchesFilter, WS_CLOSE } from '@arena/shared';
import type { WebSocket } from 'ws';

export interface Client {
  /** Unique per connection. */
  id: number;
  socket: WebSocket;
  userId: string;
  /** Lobby filter while the client watches the lobby, otherwise null. */
  lobby: RoomFilter | null;
  /** Token bucket against message floods. */
  tokens: number;
  refilledAt: number;
}

/**
 * Visible in the lobby: waiting for players and not full. Private tables are listed on their
 * own tab (joining still needs the password); tournament matches are never listed.
 */
export function isListed(room: RoomDto, scope: RoomFilter['scope'] = 'open'): boolean {
  if (room.status !== 'waiting' || room.tournament || room.seats.length >= room.settings.players) return false;
  return room.isPrivate === (scope === 'private');
}

/**
 * Knows every open socket. One live socket per user: a new connection (second tab,
 * reconnect after network change) replaces the old one.
 */
export class Hub {
  private readonly clients = new Map<string, Client>();
  private nextId = 1;

  attach(userId: string, socket: WebSocket): Client {
    const previous = this.clients.get(userId);
    if (previous && previous.socket !== socket) previous.socket.close(WS_CLOSE.REPLACED, 'replaced');
    const client: Client = { id: this.nextId++, socket, userId, lobby: null, tokens: 20, refilledAt: Date.now() };
    this.clients.set(userId, client);
    return client;
  }

  /** Returns true when this socket was the user's current one (and the user is now offline). */
  detach(client: Client): boolean {
    if (this.clients.get(client.userId) !== client) return false;
    this.clients.delete(client.userId);
    return true;
  }

  isOnline(userId: string): boolean {
    return this.clients.has(userId);
  }

  onlineUsers(): string[] {
    return [...this.clients.keys()];
  }

  send(userId: string, message: ServerMessage): void {
    const client = this.clients.get(userId);
    if (client && client.socket.readyState === client.socket.OPEN) client.socket.send(JSON.stringify(message));
  }

  sendTo(client: Client, message: ServerMessage): void {
    if (client.socket.readyState === client.socket.OPEN) client.socket.send(JSON.stringify(message));
  }

  subscribeLobby(client: Client, filter: RoomFilter | undefined, rooms: RoomDto[]): void {
    client.lobby = filter ?? EMPTY_FILTER;
    const lobbyFilter = client.lobby;
    this.sendTo(client, { type: 'LOBBY_SNAPSHOT', rooms: rooms.filter((r) => isListed(r, lobbyFilter.scope) && matchesFilter(r, lobbyFilter)) });
  }

  unsubscribeLobby(client: Client): void {
    client.lobby = null;
  }

  /** A room changed: lobby watchers whose filter matches get it, others learn it is gone. */
  publishRoom(room: RoomDto, created = false): void {
    for (const client of this.clients.values()) {
      if (!client.lobby) continue;
      if (isListed(room, client.lobby.scope) && matchesFilter(room, client.lobby)) {
        this.sendTo(client, created ? { type: 'ROOM_CREATED', room } : { type: 'ROOM_UPDATED', room });
      } else {
        this.sendTo(client, { type: 'ROOM_REMOVED', roomId: room.id });
      }
    }
  }

  /** Simple per-socket rate limit: 20 messages burst, 10 per second sustained. */
  allow(client: Client, now = Date.now()): boolean {
    client.tokens = Math.min(20, client.tokens + ((now - client.refilledAt) / 1000) * 10);
    client.refilledAt = now;
    if (client.tokens < 1) return false;
    client.tokens -= 1;
    return true;
  }

  kick(userId: string): void {
    const client = this.clients.get(userId);
    if (!client) return;
    this.clients.delete(userId);
    client.socket.close(WS_CLOSE.UNAUTHORIZED, 'banned');
  }

  closeAll(): void {
    for (const client of this.clients.values()) client.socket.close(WS_CLOSE.SERVER_SHUTDOWN, 'restart');
    this.clients.clear();
  }
}
