import websocket from '@fastify/websocket';
import { WS_CLOSE } from '@arena/shared';
import type { FastifyInstance } from 'fastify';
import { readSession } from '../auth/session.js';
import type { Context } from '../context.js';

/** How often the server pings each socket; two missed answers in a row close it. */
export const SOCKET_PING_MS = 5_000;

/** /ws?token=<session>. Telegram WebViews cannot set headers on WebSocket, hence the query token. */
export async function websocketRoutes(app: FastifyInstance, ctx: Context): Promise<void> {
  await app.register(websocket, { options: { maxPayload: 16 * 1024 } });

  app.get('/ws', { websocket: true }, (socket, request) => {
    const token = (request.query as { token?: string }).token ?? '';
    const claims = readSession(token, ctx.config.SESSION_SECRET);
    if (!claims || ctx.moderation.isBanned(claims.sub)) {
      socket.close(WS_CLOSE.UNAUTHORIZED, 'unauthorized');
      return;
    }

    // Messages that arrive while we are still attaching are queued, not lost.
    const ready = ctx.realtime.connect(claims.sub, socket);
    // A phone that lost the network keeps its socket «open» here until the ping goes unanswered.
    // Checked often: a player gone mid-turn must be seen as offline before the 15-second turn
    // runs out, so the game waits for them (the reconnect reserve) instead of a timeout loss.
    let alive = true;
    const heartbeat = setInterval(() => {
      if (!alive) return socket.terminate();
      alive = false;
      socket.ping();
    }, SOCKET_PING_MS);
    socket.on('pong', () => (alive = true));

    socket.on('message', (data) => {
      void ready.then((client) => ctx.realtime.message(client, data.toString()));
    });
    socket.on('close', () => {
      clearInterval(heartbeat);
      void ready.then((client) => ctx.realtime.disconnect(client));
    });
  });
}
