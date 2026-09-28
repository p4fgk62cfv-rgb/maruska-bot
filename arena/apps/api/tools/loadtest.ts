/**
 * Load test: many simultaneous games over real WebSockets.
 *
 *   BOT_TOKEN=… npx tsx tools/loadtest.ts --url http://localhost:8080 --games 100 --players 2
 *
 * The server must use the same BOT_TOKEN (initData is signed with it) and a high
 * AUTH_RATE_LIMIT, since every simulated player logs in from this one machine.
 * Bots decide from their own cards only (no paid hints), like a real client.
 */
import { beats, cardStrength, rankOf, type CardId, type PlayerView } from '@arena/game-engine';
import type { ServerMessage } from '@arena/shared';
import { performance } from 'node:perf_hooks';
import WebSocket from 'ws';
import { signInitData } from '../src/telegram/initData.js';

const argv = process.argv.slice(2);
const args = new Map<string, string>(argv.flatMap((a, i) => (a.startsWith('--') ? [[a, argv[i + 1] ?? ''] as [string, string]] : [])));
const BASE = args.get('--url') || 'http://localhost:8080';
const GAMES = Number(args.get('--games') || 50);
const PLAYERS = Number(args.get('--players') || 2);
const TOKEN = process.env.BOT_TOKEN ?? '';
if (!TOKEN) throw new Error('BOT_TOKEN is required');

const latencies: number[] = [];
const errors = new Map<string, number>();
let finished = 0;
let byTimeout = 0;

async function http<T>(path: string, token: string | null, body?: object): Promise<T> {
  const res = await fetch(`${BASE}/api${path}`, {
    method: body ? 'POST' : 'GET',
    headers: { 'content-type': 'application/json', ...(token ? { authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const json = (await res.json()) as T & { error?: string };
  if (!res.ok) throw new Error(`${path}: ${json.error}`);
  return json;
}

class LoadBot {
  ws!: WebSocket;
  view: PlayerView | null = null;
  private rid = 0;
  private busy = false;
  private acted = -1;
  /** After a rejection, prefer the moves that are always allowed (take / pass). */
  private safe = false;
  private pending = new Map<string, number>();
  done!: Promise<void>;

  constructor(readonly id: string, readonly token: string) {}

  async connect(): Promise<void> {
    this.ws = new WebSocket(`${BASE.replace('http', 'ws')}/ws?token=${this.token}`);
    let resolveDone!: () => void;
    this.done = new Promise((r) => (resolveDone = r));
    this.ws.on('message', (raw) => {
      const msg = JSON.parse(raw.toString()) as ServerMessage;
      if ((msg.type === 'ACK' || msg.type === 'ERROR') && msg.rid && this.pending.has(msg.rid)) {
        latencies.push(performance.now() - this.pending.get(msg.rid)!);
        this.pending.delete(msg.rid);
        this.busy = false;
        if (msg.type === 'ERROR') {
          errors.set(msg.code, (errors.get(msg.code) ?? 0) + 1);
          // Rejected (the table moved on meanwhile): decide again on the latest state, safely.
          this.acted = -1;
          this.safe = true;
        }
        this.play();
      }
      if (msg.type === 'GAME_STATE') {
        this.view = msg.state;
        this.play();
      }
      if (msg.type === 'GAME_FINISHED') {
        if (msg.result.reason === 'timeout') byTimeout++;
        resolveDone();
      }
    });
    await new Promise<void>((resolve, reject) => {
      this.ws.once('open', () => resolve());
      this.ws.once('error', reject);
    });
  }

  send(msg: object): void {
    const rid = `${++this.rid}`;
    this.pending.set(rid, performance.now());
    this.busy = true;
    this.ws.send(JSON.stringify({ ...msg, rid }));
  }

  private play(): void {
    const v = this.view;
    if (!v || this.busy || v.status !== 'playing' || v.version === this.acted || !v.you) return;
    const a = v.actions;
    const trump = v.trump.suit;
    const hand = [...v.you.hand].sort((x, y) => cardStrength(x, trump) - cardStrength(y, trump));
    const gameId = v.gameId;
    const onTable = new Set(v.table.flatMap((p) => (p.defense ? [rankOf(p.attack), rankOf(p.defense)] : [rankOf(p.attack)])));
    let move: object | null = null;

    if (v.phase === 'attack' && a.canAttack) move = { type: 'PLAY_CARD', gameId, card: hand[0] };
    else if (this.safe && a.take) move = { type: 'TAKE_CARDS', gameId };
    else if (this.safe && a.pass) move = { type: 'PASS', gameId };
    else if (a.take) {
      const index = v.table.findIndex((p) => !p.defense);
      const beater = hand.find((c) => beats(c, v.table[index]!.attack, trump));
      move = beater && Math.random() < 0.85 ? { type: 'PLAY_CARD', gameId, card: beater, target: index } : { type: 'TAKE_CARDS', gameId };
    } else if (a.pass) {
      const extra = a.canAttack ? hand.find((c: CardId) => onTable.has(rankOf(c)) && cardStrength(c, trump) < 100) : undefined;
      move = extra && Math.random() < 0.4 ? { type: 'PLAY_CARD', gameId, card: extra } : { type: 'PASS', gameId };
    }
    if (!move) return;
    this.acted = v.version;
    this.safe = false;
    // A human-ish pause so a few hundred bots behave like players, not a flood.
    // The bot counts as busy from now on, so a state arriving meanwhile does not trigger a second move.
    this.busy = true;
    setTimeout(() => this.send(move), 40 + Math.random() * 60);
  }
}

let nextTg = 600_000_000 + Math.floor(Math.random() * 100_000_000);

async function login(): Promise<LoadBot> {
  const id = nextTg++;
  const initData = signInitData({ auth_date: String(Math.floor(Date.now() / 1000)), user: JSON.stringify({ id, first_name: `Load ${id}` }) }, TOKEN);
  const { token, me } = await http<{ token: string; me: { id: string } }>('/auth/telegram', null, { initData });
  const bot = new LoadBot(me.id, token);
  await bot.connect();
  return bot;
}

async function oneTable(): Promise<void> {
  const bots = await Promise.all(Array.from({ length: PLAYERS }, login));
  const [host, ...guests] = bots;
  const { room } = await http<{ room: { id: string } }>('/rooms', host!.token, {
    stake: 100, players: PLAYERS, deckSize: 36, speed: 'normal', variant: 'podkidnoy', throwIn: 'all', fairness: 'fair', ending: 'classic', server: 'almaz', isPrivate: true, password: 'load',
  });
  for (const g of guests) await http(`/rooms/${room.id}/join`, g.token, { password: 'load' });
  for (const b of bots) b.send({ type: 'READY', roomId: room.id, ready: true });
  await Promise.all(bots.map((b) => b.done));
  finished++;
  for (const b of bots) b.ws.close();
}

const t0 = performance.now();
const results = await Promise.allSettled(Array.from({ length: GAMES }, oneTable));
const seconds = (performance.now() - t0) / 1000;
const failed = results.filter((r) => r.status === 'rejected');
latencies.sort((a, b) => a - b);
const pct = (p: number) => latencies[Math.min(latencies.length - 1, Math.floor((p / 100) * latencies.length))]?.toFixed(1);

console.log(JSON.stringify({
  games: GAMES,
  playersPerGame: PLAYERS,
  finished,
  failedToRun: failed.length,
  firstFailure: failed[0] && String((failed[0] as PromiseRejectedResult).reason),
  endedByTimeout: byTimeout,
  seconds: Number(seconds.toFixed(1)),
  actions: latencies.length,
  actionsPerSecond: Number((latencies.length / seconds).toFixed(0)),
  ackLatencyMs: { p50: pct(50), p95: pct(95), p99: pct(99), max: latencies.at(-1)?.toFixed(1) },
  errors: Object.fromEntries(errors),
}, null, 2));
process.exit(0);
