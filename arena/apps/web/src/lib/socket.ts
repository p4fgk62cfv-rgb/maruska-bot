import { errorText, type ClientMessage, type ServerMessage } from '@arena/shared';

export type SocketStatus = 'connecting' | 'open' | 'reconnecting' | 'offline' | 'closed';
type Outgoing = ClientMessage extends infer M ? (M extends { rid?: string } ? Omit<M, 'rid'> : never) : never;
export type Reply = { ok: true } | { ok: false; code: string; message: string };

/** How long a request may wait for an answer, including a resend after a reconnect. */
const TIMEOUT_MS = 12_000;
/** Silence after which an «open» socket is considered dead (a phone that slept, a lost network). */
const SILENCE_MS = 20_000;
const HEARTBEAT_MS = 8_000;
/** After the app comes back to the foreground: this long to hear from the server, or reconnect. */
const PROBE_MS = 4_000;
/** A handshake that hangs (half-dead mobile network) is given up after this long. */
const CONNECT_TIMEOUT_MS = 8_000;
const CLOSE_UNAUTHORIZED = 4001;
const CLOSE_REPLACED = 4002;

interface Waiter {
  resolve: (r: Reply) => void;
  timer: number;
  /** The exact frame, re-sent with the same id after a reconnect: the server answers it without applying it twice. */
  frame: string;
  sent: boolean;
}

const noConnection = (): Reply => ({ ok: false, code: 'NO_CONNECTION', message: errorText('NO_CONNECTION') });

/**
 * One WebSocket for the whole app. Reconnects with backoff (at once when the app is back in
 * the foreground or the network returns); after every reconnect the server pushes the current
 * room and game state, so screens just keep listening.
 */
export class GameSocket {
  status: SocketStatus = 'closed';
  /** serverTime - Date.now(), to show turn timers correctly on phones with a wrong clock. */
  clockOffset = 0;
  /** Failed attempts in a row and when the next one starts — for the reconnect indicator. */
  attempt = 0;
  nextRetryAt: number | null = null;
  private ws: WebSocket | null = null;
  private seq = 0;
  /** Request ids are «page:n»: unique per launch, so the server can recognise a resend on a new socket. */
  private readonly page = Math.random().toString(36).slice(2, 10);
  private stopped = true;
  private retryTimer: number | undefined;
  private heartbeat: number | undefined;
  private probeTimer: number | undefined;
  private lastHeard = 0;
  private pending = new Map<string, Waiter>();
  private messageListeners = new Set<(m: ServerMessage) => void>();
  private statusListeners = new Set<(s: SocketStatus) => void>();
  private openListeners = new Set<() => void>();

  constructor(
    private readonly token: () => string | null,
    /** The server refused the session (expired): renew it; true when the socket may try again. */
    private readonly renew: () => Promise<boolean> = async () => false,
  ) {}

  start(): void {
    this.stopped = false;
    window.addEventListener('online', this.wake);
    window.addEventListener('offline', this.lost);
    window.addEventListener('pageshow', this.wake);
    document.addEventListener('visibilitychange', this.onVisibility);
    this.open();
  }

  stop(): void {
    this.stopped = true;
    window.removeEventListener('online', this.wake);
    window.removeEventListener('offline', this.lost);
    window.removeEventListener('pageshow', this.wake);
    document.removeEventListener('visibilitychange', this.onVisibility);
    window.clearTimeout(this.retryTimer);
    window.clearTimeout(this.probeTimer);
    window.clearInterval(this.heartbeat);
    const ws = this.ws;
    this.ws = null;
    ws?.close();
    this.failPending();
    this.setStatus('closed');
  }

  /** «Повторить сейчас» on the indicator. */
  retryNow(): void {
    if (this.stopped || this.status === 'open' || this.status === 'connecting') return;
    window.clearTimeout(this.retryTimer);
    this.open();
  }

  send(msg: Outgoing): Promise<Reply> {
    const rid = `${this.page}:${++this.seq}`;
    return new Promise((resolve) => {
      // While reconnecting a request waits for the socket instead of failing at once.
      if (this.stopped || this.status === 'closed') return resolve(noConnection());
      const timer = window.setTimeout(() => {
        this.pending.delete(rid);
        resolve(noConnection());
      }, TIMEOUT_MS);
      const waiter: Waiter = { resolve, timer, frame: JSON.stringify({ ...msg, rid }), sent: false };
      this.pending.set(rid, waiter);
      this.flush(waiter);
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

  private flush(waiter: Waiter): void {
    if (this.status !== 'open' || this.ws?.readyState !== WebSocket.OPEN) return;
    this.ws.send(waiter.frame);
    waiter.sent = true;
  }

  private failPending(): void {
    for (const [rid, waiter] of this.pending) {
      window.clearTimeout(waiter.timer);
      waiter.resolve(noConnection());
      this.pending.delete(rid);
    }
  }

  private open(): void {
    const token = this.token();
    if (!token || this.stopped) return;
    this.nextRetryAt = null;
    this.setStatus(this.attempt === 0 ? 'connecting' : 'reconnecting');
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${scheme}://${location.host}/ws?token=${encodeURIComponent(token)}`);
    this.ws = ws;
    window.clearTimeout(this.probeTimer);
    this.probeTimer = window.setTimeout(() => {
      if (this.ws === ws && ws.readyState === WebSocket.CONNECTING) this.dropped();
    }, CONNECT_TIMEOUT_MS);

    ws.onopen = () => {
      if (this.ws !== ws) return;
      window.clearTimeout(this.probeTimer);
      this.attempt = 0;
      this.lastHeard = Date.now();
      this.setStatus('open');
      this.ping(true);
      // Requests made while the network was gone (or whose answer was lost) go out now.
      for (const waiter of this.pending.values()) this.flush(waiter);
      window.clearInterval(this.heartbeat);
      this.heartbeat = window.setInterval(() => this.checkAlive(), HEARTBEAT_MS);
      for (const l of this.openListeners) l();
    };
    ws.onmessage = (event) => {
      if (this.ws !== ws) return;
      this.lastHeard = Date.now();
      window.clearTimeout(this.probeTimer);
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
      this.dropped(event.code);
    };
  }

  /** The socket is gone: unanswered requests wait for the next one (they keep their ids). */
  private dropped(code?: number): void {
    window.clearInterval(this.heartbeat);
    window.clearTimeout(this.probeTimer);
    const ws = this.ws;
    this.ws = null;
    if (ws && ws.readyState <= WebSocket.OPEN) {
      ws.onclose = null;
      ws.close();
    }
    for (const waiter of this.pending.values()) waiter.sent = false;
    // Replaced by another tab or not authorised: do not fight for the connection.
    if (code === CLOSE_UNAUTHORIZED && !this.stopped) {
      // Usually an app left open past its session: renew it and come back without a restart.
      this.setStatus('reconnecting');
      void this.renew().then((ok) => {
        if (this.stopped) return;
        if (ok) this.open();
        else {
          this.failPending();
          this.setStatus('closed');
        }
      });
      return;
    }
    if (this.stopped || code === CLOSE_REPLACED) {
      this.failPending();
      this.setStatus('closed');
      return;
    }
    this.attempt++;
    if (!navigator.onLine) {
      // No network at all: wait for the «online» event instead of burning attempts.
      this.setStatus('offline');
      return;
    }
    const delay = this.attempt === 1 ? 300 : Math.min(8_000, 500 * 2 ** Math.min(this.attempt - 1, 5)) * (0.75 + Math.random() * 0.5);
    this.nextRetryAt = Date.now() + delay;
    this.setStatus('reconnecting');
    window.clearTimeout(this.retryTimer);
    this.retryTimer = window.setTimeout(() => this.open(), delay);
  }

  private ping(measureClock = false): void {
    const sentAt = Date.now();
    void this.send({ type: 'PING' });
    if (!measureClock) return;
    const off = this.onMessage((m) => {
      if (m.type !== 'PONG') return;
      this.clockOffset = m.serverTime - (sentAt + Date.now()) / 2;
      off();
    });
  }

  /** A socket can look open while the phone slept or switched networks: silence means it is dead. */
  private checkAlive(): void {
    if (this.status !== 'open') return;
    if (Date.now() - this.lastHeard > SILENCE_MS) return this.dropped();
    if (Date.now() - this.lastHeard > HEARTBEAT_MS) this.ping();
  }

  /** Back to the foreground or back online: check the socket right away instead of waiting. */
  private readonly wake = (): void => {
    if (this.stopped) return;
    if (this.status === 'open') {
      this.ping();
      window.clearTimeout(this.probeTimer);
      const since = Date.now();
      this.probeTimer = window.setTimeout(() => {
        if (this.status === 'open' && this.lastHeard < since) this.dropped();
      }, PROBE_MS);
    } else if (this.status === 'reconnecting' || this.status === 'offline') {
      window.clearTimeout(this.retryTimer);
      this.open();
    }
  };

  private readonly lost = (): void => {
    if (this.stopped) return;
    if (this.status === 'open') this.dropped();
    else if (this.status === 'reconnecting') {
      window.clearTimeout(this.retryTimer);
      this.nextRetryAt = null;
      this.setStatus('offline');
    }
  };

  private readonly onVisibility = (): void => {
    if (document.visibilityState === 'visible') this.wake();
  };

  private setStatus(status: SocketStatus): void {
    this.status = status;
    for (const l of this.statusListeners) l(status);
  }
}
