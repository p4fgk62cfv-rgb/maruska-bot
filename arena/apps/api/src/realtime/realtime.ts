import { clientMessageSchema } from '@arena/shared/schemas';
import type { AppErrorCode, ClientMessage } from '@arena/shared';
import type { FastifyBaseLogger } from 'fastify';
import type { WebSocket } from 'ws';
import type { Config } from '../config.js';
import type { Db } from '../db.js';
import { AppError } from '../lib/errors.js';
import type { Ledger } from '../services/ledger.js';
import { SettlementService } from '../services/settlement.js';
import type { UserService } from '../services/users.js';
import { GameManager, wsError } from './games.js';
import { Hub, type Client } from './hub.js';
import { RoomManager } from './rooms.js';
import type { SnapshotStore } from './store.js';

export interface RealtimeDeps {
  config: Config;
  db: Db;
  ledger: Ledger;
  users: UserService;
  store: SnapshotStore;
  log: FastifyBaseLogger;
}

/** Wires the hub, rooms and games together and speaks the WebSocket protocol. */
export class Realtime {
  readonly hub = new Hub();
  readonly rooms: RoomManager;
  readonly games: GameManager;
  readonly settlement: SettlementService;

  constructor(private readonly deps: RealtimeDeps) {
    this.settlement = new SettlementService(deps.db, deps.ledger, deps.config.RAKE_PERCENT);
    this.rooms = new RoomManager({ ...deps, hub: this.hub, games: () => this.games });
    this.games = new GameManager({
      db: deps.db,
      hub: this.hub,
      store: deps.store,
      ledger: deps.ledger,
      settlement: this.settlement,
      log: deps.log,
      onFinished: (roomId, result) => this.rooms.finished(roomId, result),
    });
  }

  /**
   * Boot: bring back rooms and games from the snapshot store. Games that the database
   * still shows as running but that nobody can resume are aborted with refunds.
   */
  async recover(): Promise<void> {
    const { rooms, games } = await this.deps.store.loadAll();
    for (const room of rooms) this.rooms.restore(room);
    const restored = new Set<string>();
    for (const game of games) {
      const room = rooms.find((r) => r.id === game.roomId);
      const players = (room?.seats ?? []).map((s) => ({ ...s, connected: false }));
      if (!room || players.length !== game.state.players.length) continue;
      await this.games.restore(game, players.map(({ userId, name, photoUrl, rating, premium, connected }) => ({ userId, name, photoUrl, rating, premium, connected })));
      restored.add(game.gameId);
    }
    const orphans = await this.deps.db.game.findMany({ where: { status: 'PLAYING' }, select: { id: true } });
    for (const { id } of orphans) {
      if (restored.has(id)) continue;
      await this.settlement.abort(id);
      this.deps.log.warn({ gameId: id }, 'aborted unrecoverable game, stakes refunded');
    }
  }

  async connect(userId: string, socket: WebSocket): Promise<Client> {
    const client = this.hub.attach(userId, socket);
    const room = await this.rooms.connected(userId);
    if (room) {
      const game = room.gameId ? this.games.get(room.gameId) : undefined;
      this.hub.sendTo(client, { type: 'ROOM_UPDATED', room: this.rooms.dto(room) });
      game?.sendState(userId);
    }
    return client;
  }

  async disconnect(client: Client): Promise<void> {
    if (this.hub.detach(client)) await this.rooms.disconnected(client.userId);
  }

  async message(client: Client, raw: string): Promise<void> {
    let msg: ClientMessage;
    try {
      msg = clientMessageSchema.parse(JSON.parse(raw));
    } catch {
      return this.hub.sendTo(client, wsError('VALIDATION_FAILED'));
    }
    // Answer with the rid so the client knows this exact request was dropped and may retry.
    if (!this.hub.allow(client)) return this.hub.sendTo(client, wsError('RATE_LIMITED', msg.rid));

    // A resent request (flaky mobile network) is acknowledged but never applied twice.
    if (msg.rid) {
      if (client.seen.has(msg.rid)) return this.hub.sendTo(client, { type: 'ACK', rid: msg.rid });
      client.seen.add(msg.rid);
      if (client.seen.size > 200) client.seen.delete(client.seen.values().next().value!);
    }

    try {
      await this.dispatch(client, msg);
      if (msg.rid) this.hub.sendTo(client, { type: 'ACK', rid: msg.rid });
    } catch (error) {
      if (msg.rid) client.seen.delete(msg.rid);
      const code: AppErrorCode = error instanceof AppError ? error.code : 'SERVER_ERROR';
      if (!(error instanceof AppError)) this.deps.log.error({ err: error, type: msg.type }, 'ws handler failed');
      this.hub.sendTo(client, wsError(code, msg.rid));
    }
  }

  private async dispatch(client: Client, msg: ClientMessage): Promise<void> {
    const { userId } = client;
    switch (msg.type) {
      case 'PING':
        return this.hub.sendTo(client, { type: 'PONG', rid: msg.rid, serverTime: Date.now() });
      case 'LOBBY_SUBSCRIBE':
        return this.hub.subscribeLobby(client, msg.filter, this.rooms.list());
      case 'LOBBY_UNSUBSCRIBE':
        return this.hub.unsubscribeLobby(client);
      case 'ROOM_WATCH':
      case 'RECONNECT': {
        const room = this.rooms.get(msg.roomId);
        if (!room || !room.seats.some((s) => s.userId === userId)) throw new AppError('NOT_FOUND');
        this.hub.sendTo(client, { type: 'ROOM_UPDATED', room: this.rooms.dto(room) });
        if (room.gameId) this.games.get(room.gameId)?.sendState(userId);
        return;
      }
      case 'READY':
        return this.rooms.setReady(userId, msg.roomId, msg.ready);
      default:
        return this.games.handle(userId, msg);
    }
  }

  async shutdown(): Promise<void> {
    this.rooms.shutdown();
    await this.games.shutdown();
    this.hub.closeAll();
    await this.deps.store.close();
  }
}
