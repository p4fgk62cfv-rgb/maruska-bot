import {
  newGame,
  policyMove,
  stepGame,
  SUIT_SYMBOL,
  rankOf,
  suitOf,
  type BrainParams,
  type CardId,
  type GameEvent,
  type GameState,
} from '@arena/game-engine';
import type { ServerMessage, TrainingTableDto } from '@arena/shared';
import { TRAINING_TABLES } from './training.js';

/** One move this often (a bit of jitter), so a person can follow the game. */
const MOVE_MS = 1100;
/** The finished game stays on the table this long before a new deal. */
const RESULT_MS = 5000;

type Role = 'champion' | 'challenger';

interface Table {
  key: string;
  title: string;
  settings: (typeof TRAINING_TABLES)[number]['settings'];
  game: number;
  score: { champion: number; challenger: number };
  roles: Record<string, Role>;
  names: Record<string, string>;
  state: GameState | null;
  called: Set<number>;
  last: string | null;
  result: string | null;
  nextAt: number;
}

export interface ShowcaseDeps {
  publish: (message: ServerMessage) => void;
  watched: () => boolean;
  /** The champion and the copy being tried now (from the trainer); null — the trained weights. */
  players: () => { champion: BrainParams; challenger: BrainParams; version: number } | null;
  fallback: () => { params: BrainParams; version: number };
}

/**
 * The three training tables people can watch: the current champion plays the copy that the
 * self-play is trying right now, at a human pace and with every hand open. The real training
 * runs thousands of games a minute in the background; these show what it looks like.
 */
export class Showcase {
  private readonly tables: Table[] = TRAINING_TABLES.map((t) => ({
    key: t.key,
    title: t.title,
    settings: t.settings,
    game: 0,
    score: { champion: 0, challenger: 0 },
    roles: {},
    names: {},
    state: null,
    called: new Set(),
    last: null,
    result: null,
    nextAt: 0,
  }));
  private timer: NodeJS.Timeout | null = null;

  constructor(private readonly deps: ShowcaseDeps) {}

  start(): void {
    if (this.timer) return;
    for (const t of this.tables) this.deal(t);
    this.timer = setInterval(() => this.tick(), 250);
    this.timer.unref();
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  snapshot(): TrainingTableDto[] {
    return this.tables.filter((t) => t.state).map((t) => this.dto(t));
  }

  private players() {
    const live = this.deps.players();
    if (live) return live;
    const { params, version } = this.deps.fallback();
    return { champion: params, challenger: params, version };
  }

  private deal(t: Table): void {
    const { version } = this.players();
    t.game++;
    const n = t.settings.players;
    // Seats move round every game: the challenger sits everywhere in turn.
    const ids = Array.from({ length: n }, (_, i) => `s${i}`);
    const hero = ids[t.game % n]!;
    t.roles = Object.fromEntries(ids.map((id) => [id, id === hero ? 'challenger' : 'champion']));
    let k = 0;
    t.names = Object.fromEntries(ids.map((id) => [id, id === hero ? 'Претендент' : n > 2 ? `Чемпион v${version} · ${++k}` : `Чемпион v${version}`]));
    t.state = newGame(t.settings, ids, Math.random);
    t.called = new Set();
    t.last = 'Новая раздача';
    t.result = null;
    t.nextAt = Date.now() + MOVE_MS;
  }

  private tick(): void {
    const now = Date.now();
    for (const t of this.tables) {
      if (!t.state || now < t.nextAt) continue;
      if (t.result) {
        this.deal(t);
        this.publish(t);
        continue;
      }
      const { champion, challenger } = this.players();
      const step = stepGame(
        t.state,
        (s, id) => policyMove(s, id, t.roles[id] === 'challenger' ? challenger : champion, Math.random, 0.05),
        Math.random,
        champion.catchRate,
        t.called,
      );
      if (!step) {
        this.deal(t);
        this.publish(t);
        continue;
      }
      t.state = step.state;
      t.last = describe(step.events, t.names) ?? t.last;
      t.nextAt = now + MOVE_MS * (0.7 + Math.random() * 0.6);
      if (step.state.status === 'finished') {
        const res = step.state.result;
        if (res?.kind === 'loser') {
          const role = t.roles[res.loser]!;
          // A point to the side that did not lose.
          if (role === 'champion') t.score.challenger++;
          else t.score.champion++;
          t.result = `Дурак — ${t.names[res.loser]}`;
        } else t.result = 'Ничья';
        t.nextAt = now + RESULT_MS;
      }
      this.publish(t);
    }
  }

  private publish(t: Table): void {
    if (this.deps.watched()) this.deps.publish({ type: 'TRAINING_TABLE', table: this.dto(t) });
  }

  private dto(t: Table): TrainingTableDto {
    const s = t.state!;
    return {
      key: t.key,
      title: t.title,
      game: t.game,
      score: t.score,
      championVersion: this.players().version,
      seats: s.players.map((p) => ({
        id: p.id,
        name: t.names[p.id] ?? p.id,
        role: t.roles[p.id] ?? 'champion',
        hand: [...p.hand],
        status: p.status,
        attacker: s.status === 'playing' && p.id === s.attacker,
        defender: s.status === 'playing' && p.id === s.defender,
      })),
      table: s.table.map((p) => ({ attack: p.attack, defense: p.defense })),
      trump: { card: s.trump.card, inStock: s.deck.length > 0 },
      deck: s.deck.length,
      discard: s.discard.length,
      last: t.last,
      result: t.result,
    };
  }
}

const RANK_RU: Record<string, string> = { J: 'В', Q: 'Д', K: 'К', A: 'Т' };
const cardText = (c: CardId) => `${RANK_RU[rankOf(c)] ?? rankOf(c)}${SUIT_SYMBOL[suitOf(c)]}`;

/** The step's main event in words. */
function describe(events: GameEvent[], names: Record<string, string>): string | null {
  const who = (id: string) => names[id] ?? id;
  const played = events.filter((e) => e.type === 'CARD_PLAYED');
  for (const e of events) {
    if (e.type === 'CHEAT_CAUGHT') return `${who(e.reporter)} ловит на жульничестве: ${who(e.cheater)}`;
    if (e.type === 'CARD_TRANSFERRED') return `${who(e.playerId)} переводит ${cardText(e.card)}`;
    if (e.type === 'TAKE_DECLARED') return `${who(e.playerId)} берёт`;
    if (e.type === 'PLAYER_OUT') return `${who(e.playerId)} вышел из игры`;
  }
  if (played.length) {
    const first = played[0]!;
    if (first.type !== 'CARD_PLAYED') return null;
    const cards = played.map((e) => (e.type === 'CARD_PLAYED' ? cardText(e.card) : '')).join(' ');
    if (first.role === 'defense') return `${who(first.playerId)} бьёт ${cards}`;
    return `${who(first.playerId)} ходит ${cards}`;
  }
  for (const e of events) {
    if (e.type === 'ROUND_FINISHED') return e.outcome === 'beaten' ? 'Бито' : 'Карты забраны';
    if (e.type === 'PASSED') return `${who(e.playerId)}: пас`;
  }
  return null;
}
