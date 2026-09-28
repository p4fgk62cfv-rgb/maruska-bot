import { errorText, type ClientMessage, type ServerMessage } from '@arena/shared';

export type SocketStatus = 'connecting' | 'open' | 'reconnecting' | 'closed';
type Outgoing = ClientMessage extends infer M ? (M extends { rid?: string } ? Omit<M, 'rid'> : never) : never;
export type Reply = { ok: true } | { ok: false; code: string; message: string };

const TIMEOUT_MS = 10_000;
const CLOSE_UNAUTHORIZED = 4001;
const CLOSE_REPLACED = 4002;

/**
 * One WebSocket for the whole app. Reconnects with backoff; after every reconnect the
 * server pushes the current room and game state, so screens just keep listening.
 */
export class GameSocket {
  status: SocketStatus = 'closed';
  /** serverTime - Date.now(), to show turn timers correctly on phones with a wrong clock. */
  clockOffset = 0;
  private ws: WebSocket | null = null;
  private attempt = 0;
  private seq = 0;
  private stopped = true;
  private retryTimer: number | undefined;
  private pending = new Map<string, { resolve: (r: Reply) => void; timer: number }>();
  private messageListeners = new Set<(m: ServerMessage) => void>();
  private statusListeners = new Set<(s: SocketStatus) => void>();
  private openListeners = new Set<() => void>();

  constructor(private readonly token: () => string | null) {}

  start(): void {
    this.stopped = false;
    this.open();
  }

  stop(): void {
    this.stopped = true;
    window.clearTimeout(this.retryTimer);
    this.ws?.close();
    this.setStatus('closed');
  }

  send(msg: Outgoing): Promise<Reply> {
    const rid = `c${++this.seq}`;
    return new Promise((resolve) => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
        resolve({ ok: false, code: 'NO_CONNECTION', message: errorText('NO_CONNECTION') });
        return;
      }
      const timer = window.setTimeout(() => {
        this.pending.delete(rid);
        resolve({ ok: false, code: 'NO_CONNECTION', message: errorText('NO_CONNECTION') });
      }, TIMEOUT_MS);
      this.pending.set(rid, { resolve, timer });
      this.ws.send(JSON.stringify({ ...msg, rid }));
    });
  }

  onMessage(listener: (m: ServerMessage) => void): () => void {
    this.messageListeners.add(listener);
    return () => this.messageListeners.delete(listener);
  }

  onStatus(listener: (s: SocketStatus) => void): () => void {
    this.statusListeners.add(listener);
    return () => this.statusListeners.delete(listener);
  }

  /** Called on every (re)connect: the place to re-subscribe to the lobby. */
  onOpen(listener: () => void): () => void {
    this.openListeners.add(listener);
    if (this.status === 'open') listener();
    return () => this.openListeners.delete(listener);
  }

  now(): number {
    return Date.now() + this.clockOffset;
  }

  private open(): void {
    const token = this.token();
    if (!token || this.stopped) return;
    this.setStatus(this.attempt === 0 ? 'connecting' : 'reconnecting');
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${scheme}://${location.host}/ws?token=${encodeURIComponent(token)}`);
    this.ws = ws;

    ws.onopen = () => {
      this.attempt = 0;
      this.setStatus('open');
      const sentAt = Date.now();
      void this.send({ type: 'PING' });
      const off = this.onMessage((m) => {
        if (m.type !== 'PONG') return;
        this.clockOffset = m.serverTime - (sentAt + Date.now()) / 2;
        off();
      });
      for (const l of this.openListeners) l();
    };
    ws.onmessage = (event) => {
      const msg = JSON.parse(String(event.data)) as ServerMessage;
      if ((msg.type === 'ACK' || msg.type === 'ERROR') && msg.rid) {
        const waiter = this.pending.get(msg.rid);
        if (waiter) {
          window.clearTimeout(waiter.timer);
          this.pending.delete(msg.rid);
          waiter.resolve(msg.type === 'ACK' ? { ok: true } : { ok: false, code: msg.code, message: msg.message });
        }
      }
      for (const l of this.messageListeners) l(msg);
    };
    ws.onclose = (event) => {
      if (this.ws !== ws) return;
      for (const [rid, waiter] of this.pending) {
        window.clearTimeout(waiter.timer);
        waiter.resolve({ ok: false, code: 'NO_CONNECTION', message: errorText('NO_CONNECTION') });
        this.pending.delete(rid);
      }
      // Replaced by another tab or not authorised: do not fight for the connection.
      if (this.stopped || event.code === CLOSE_REPLACED || event.code === CLOSE_UNAUTHORIZED) {
        this.setStatus('closed');
        return;
      }
      this.attempt++;
      this.setStatus('reconnecting');
      const delay = Math.min(10_000, 500 * 2 ** Math.min(this.attempt, 5)) * (0.75 + Math.random() * 0.5);
      this.retryTimer = window.setTimeout(() => this.open(), delay);
    };
  }

  private setStatus(status: SocketStatus): void {
    this.status = status;
    for (const l of this.statusListeners) l(status);
  }
}
