import { cardStrength, type CardId, type PlayerView } from '@arena/game-engine';
import type { ClientMessage, GameResultDto, ServerMessage } from '@arena/shared';
import WebSocket from 'ws';

type Outgoing = ClientMessage extends infer M ? (M extends { rid?: string } ? Omit<M, 'rid'> : never) : never;

/** A test player speaking the real WebSocket protocol. Plays legal moves from the hints it receives. */
export class Bot {
  ws!: WebSocket;
  inbox: ServerMessage[] = [];
  view: PlayerView | null = null;
  result: GameResultDto | null = null;
  gameId: string | null = null;
  autoplay = false;
  closedWith: number | null = null;
  private rid = 0;
  private waiters: { pred: (m: ServerMessage) => boolean; resolve: (m: ServerMessage) => void }[] = [];
  private actedOn = -1;
  private busy = false;

  constructor(readonly name: string, readonly userId: string, private readonly token: string, private readonly base: string) {}

  async connect(token = this.token): Promise<void> {
    this.ws = new WebSocket(`${this.base.replace('http', 'ws')}/ws?token=${token}`);
    this.ws.on('message', (data) => this.receive(JSON.parse(data.toString()) as ServerMessage));
    this.ws.on('close', (code) => (this.closedWith = code));
    await new Promise<void>((resolve, reject) => {
      this.ws.once('open', () => resolve());
      this.ws.once('error', reject);
    });
  }

  close(): void {
    this.ws.close();
  }

  send(msg: Outgoing): Promise<ServerMessage> {
    const rid = `${this.name}-${++this.rid}`;
    const reply = this.waitFor((m) => (m.type === 'ACK' || m.type === 'ERROR') && m.rid === rid);
    this.ws.send(JSON.stringify({ ...msg, rid }));
    return reply;
  }

  waitFor(pred: (m: ServerMessage) => boolean, timeoutMs = 10_000): Promise<ServerMessage> {
    const found = this.inbox.find(pred);
    if (found) return Promise.resolve(found);
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`${this.name}: timed out waiting`)), timeoutMs);
      this.waiters.push({ pred, resolve: (m) => (clearTimeout(timer), resolve(m)) });
    });
  }

  private receive(msg: ServerMessage): void {
    this.inbox.push(msg);
    if (msg.type === 'GAME_STARTED') this.gameId = msg.gameId;
    if (msg.type === 'GAME_STATE') {
      this.view = msg.state;
      this.gameId = msg.state.gameId;
    }
    if (msg.type === 'GAME_FINISHED') this.result = msg.result;
    this.waiters = this.waiters.filter((w) => (w.pred(msg) ? (w.resolve(msg), false) : true));
    if (msg.type === 'GAME_STATE' && this.autoplay) this.play();
  }

  /** Like a real client: one move in flight at a time, a short human-ish pause, retry when throttled. */
  private async move(msg: Outgoing, version: number): Promise<void> {
    this.busy = true;
    await new Promise((r) => setTimeout(r, 20));
    const reply = await this.send(msg).catch(() => null);
    this.busy = false;
    if (reply?.type === 'ERROR' && reply.code === 'RATE_LIMITED') this.actedOn = version - 1;
    if (this.autoplay) this.play();
  }

  /** One decision per state version: throw in rarely, beat with the cheapest card, otherwise take or pass. */
  private play(): void {
    const v = this.view;
    if (!v || this.busy || v.status !== 'playing' || v.version === this.actedOn || !this.gameId) return;
    const a = v.actions;
    const trump = v.trump.suit;
    const cheapest = (cards: CardId[]) => [...cards].sort((x, y) => cardStrength(x, trump) - cardStrength(y, trump))[0];
    const gameId = this.gameId;
    let move: Outgoing | null = null;

    if (v.phase === 'attack' && a.canAttack && a.attack.length) move = { type: 'PLAY_CARD', gameId, card: cheapest(a.attack)! };
    else if (a.take || Object.keys(a.defend).length) {
      const options = Object.entries(a.defend) as [CardId, number[]][];
      const best = options.sort(([x], [y]) => cardStrength(x, trump) - cardStrength(y, trump))[0];
      move = best && Math.random() < 0.85 ? { type: 'PLAY_CARD', gameId, card: best[0], target: best[1][0]! } : { type: 'TAKE_CARDS', gameId };
    } else if (a.pass) {
      move = a.attack.length && Math.random() < 0.3 ? { type: 'PLAY_CARD', gameId, card: cheapest(a.attack)! } : { type: 'PASS', gameId };
    }
    if (!move) return;
    this.actedOn = v.version;
    void this.move(move, v.version);
  }

  latest<T extends ServerMessage['type']>(type: T): Extract<ServerMessage, { type: T }> | undefined {
    return [...this.inbox].reverse().find((m) => m.type === type) as Extract<ServerMessage, { type: T }> | undefined;
  }
}
