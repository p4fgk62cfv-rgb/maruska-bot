import websocket from '@fastify/websocket';
import { WS_CLOSE } from '@arena/shared';
import type { FastifyInstance } from 'fastify';
import { readSession } from '../auth/session.js';
import type { Context } from '../context.js';

/** /ws?token=<session>. Telegram WebViews cannot set headers on WebSocket, hence the query token. */
export async function websocketRoutes(app: FastifyInstance, ctx: Context): Promise<void> {
  await app.register(websocket, { options: { maxPayload: 16 * 1024 } });

  app.get('/ws', { websocket: true }, (socket, request) => {
    const token = (request.query as { token?: string }).token ?? '';
    const claims = readSession(token, ctx.config.SESSION_SECRET);
    if (!claims) {
      socket.close(WS_CLOSE.UNAUTHORIZED, 'unauthorized');
      return;
    }

    // Messages that arrive while we are still attaching are queued, not lost.
    const ready = ctx.realtime.connect(claims.sub, socket);
    let alive = true;
    const heartbeat = setInterval(() => {
      if (!alive) return socket.terminate();
      alive = false;
      socket.ping();
    }, 25_000);
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
