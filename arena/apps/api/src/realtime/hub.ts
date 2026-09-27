import type { RoomDto, RoomFilter, ServerMessage } from '@arena/shared';
import { EMPTY_FILTER, matchesFilter, WS_CLOSE } from '@arena/shared';
import type { WebSocket } from 'ws';

export interface Client {
  socket: WebSocket;
  userId: string;
  /** Lobby filter while the client watches the lobby, otherwise null. */
  lobby: RoomFilter | null;
  /** Recently seen request ids: a resent message is acknowledged but not applied twice. */
  seen: Set<string>;
  /** Token bucket against message floods. */
  tokens: number;
  refilledAt: number;
}

/** Visible in the lobby: waiting for players and not full. */
export function isListed(room: RoomDto): boolean {
  return room.status === 'waiting' && !room.isPrivate && room.seats.length < room.settings.players;
}

/**
 * Knows every open socket. One live socket per user: a new connection (second tab,
 * reconnect after network change) replaces the old one.
 */
export class Hub {
  private readonly clients = new Map<string, Client>();

  attach(userId: string, socket: WebSocket): Client {
    const previous = this.clients.get(userId);
    if (previous && previous.socket !== socket) previous.socket.close(WS_CLOSE.REPLACED, 'replaced');
    const client: Client = { socket, userId, lobby: null, seen: new Set(), tokens: 20, refilledAt: Date.now() };
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
    this.sendTo(client, { type: 'LOBBY_SNAPSHOT', rooms: rooms.filter((r) => isListed(r) && matchesFilter(r, lobbyFilter)) });
  }

  unsubscribeLobby(client: Client): void {
    client.lobby = null;
  }

  /** A room changed: lobby watchers whose filter matches get it, others learn it is gone. */
  publishRoom(room: RoomDto, created = false): void {
    const listed = isListed(room);
    for (const client of this.clients.values()) {
      if (!client.lobby) continue;
      if (listed && matchesFilter(room, client.lobby)) {
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

  closeAll(): void {
    for (const client of this.clients.values()) client.socket.close(WS_CLOSE.SERVER_SHUTDOWN, 'restart');
    this.clients.clear();
  }
}
