// Self-play training in its own thread: three tables play all day, the best weights win.
import { parentPort, workerData } from 'node:worker_threads';
import {
  chooseBotMove,
  mutateParams,
  newGame,
  policyMove,
  rememberEvents,
  runGame,
  searchMove,
  solveEndgame,
  toPlayerView,
  type BrainParams,
  type CardMemory,
  type Decider,
  type GameSettings,
} from '@arena/game-engine';
import { TRAINING_TABLES, type TrainerInit, type TrainerMessage, type TrainingExam } from './training.js';

const init = workerData as TrainerInit;
let champion: BrainParams = init.champion;
let version = init.version;
let sigma = init.sigma ?? 0.25;
/** Share of time spent playing (the rest the thread sleeps, leaving the CPU to the games). */
const duty = Math.min(0.9, Math.max(0.05, init.duty));

const post = (m: TrainerMessage) => parentPort!.postMessage(m);
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const mulberry = (seed: number) => {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
};
let seedCounter = Math.floor(Math.random() * 1e9);

/**
 * One deal played twice with the seats swapped (luck of the cards cancels out). Returns how much
 * better than an even share the challenger did: +½ — never the fool, −½ — the fool both times.
 */
function mirrored(settings: GameSettings, challenger: BrainParams, base: BrainParams): number {
  const n = settings.players;
  const seed = seedCounter++;
  let score = 0;
  for (const seat of [0, 1]) {
    const ids = Array.from({ length: n }, (_, i) => `p${i}`);
    const hero = ids[seat === 0 ? 0 : n - 1]!;
    const rnd = mulberry(seed);
    const start = newGame(settings, ids, rnd);
    const play = mulberry(seed * 31 + seat);
    const decide: Decider = (s, id) => policyMove(s, id, id === hero ? challenger : base, play, 0.05);
    const end = runGame(start, decide, play, base.catchRate);
    const fool = end.result?.kind === 'loser' ? end.result.loser : null;
    // Even share: the fool is one of n players.
    score += (fool === hero ? 0 : 1) - (n - 1) / n;
  }
  return score / 2;
}

const oldHard: Decider = (s, id) => {
  if (s.deck.length === 0 && s.players.length === 2) {
    const m = solveEndgame(s, id);
    if (m) return m;
  }
  return chooseBotMove(toPlayerView(s, id, { hints: true, discard: true }), 'hard');
};

/** The new strong bot (search with the champion weights) against the old «максимальный». */
async function exam(): Promise<TrainingExam> {
  const settings: GameSettings = { variant: 'podkidnoy', throwIn: 'all', fairness: 'fair', ending: 'classic', deckSize: 36, players: 2, speed: 'normal' };
  let won = 0;
  let played = 0;
  const games = init.examGames;
  for (let g = 0; g < games; g++) {
    const t0 = Date.now();
    const seed = seedCounter++;
    const ids = ['new', 'old'];
    const me = 'new';
    const rnd = mulberry(seed);
    let s = newGame({ ...settings, variant: g % 2 ? 'perevodnoy' : 'podkidnoy' }, g % 4 < 2 ? ids : [...ids].reverse(), rnd);
    const play = mulberry(seed + 1);
    let memory: CardMemory = {};
    // Play move by move to keep the public memory, as the server does.
    const decide: Decider = (st, id) => {
      if (id !== me) return oldHard(st, id);
      if (st.deck.length === 0 && st.players.length === 2) {
        const m = solveEndgame(st, id);
        if (m) return m;
      }
      return searchMove(st, id, memory, champion, { iterations: init.examIterations, budgetMs: 2000, random: play });
    };
    s = runGame(s, decide, play, champion.catchRate, 600, (events) => (memory = rememberEvents(memory, events)));
    if (s.result?.kind === 'loser') {
      played++;
      if (s.result.loser !== me) won++;
    }
    await sleep(((Date.now() - t0) * (1 - duty)) / duty);
  }
  return { at: new Date().toISOString(), games: played, winRate: played ? won / played : 0 };
}

async function main(): Promise<void> {
  let lastExam = 0;
  for (;;) {
    // ── one generation: a challenger near the champion plays a batch on every table ──
    const challenger = mutateParams(champion, sigma, Math.random);
    post({ type: 'challenger', params: challenger, champion, version });
    const results: number[] = [];
    const perTable: number[] = TRAINING_TABLES.map(() => 0);
    const confirm = async (deals: number) => {
      for (let i = 0; i < deals; i++) {
        const t0 = Date.now();
        for (let t = 0; t < TRAINING_TABLES.length; t++) {
          const score = mirrored(TRAINING_TABLES[t]!.settings, challenger, champion);
          results.push(score);
          perTable[t]! += 2;
        }
        await sleep(((Date.now() - t0) * (1 - duty)) / duty);
      }
    };
    await confirm(init.dealsPerGeneration);
    let z = zScore(results);
    // A promising challenger plays a second, bigger batch before it may take over.
    if (z > 2) {
      await confirm(init.dealsPerGeneration * 2);
      z = zScore(results);
    }
    const promoted = z > 2.5;
    if (promoted) {
      champion = challenger;
      version++;
      sigma = Math.min(0.5, sigma * 1.15);
    } else sigma = Math.max(0.03, sigma * 0.98);
    post({ type: 'generation', games: perTable, promoted, version, sigma, score: mean(results), params: promoted ? champion : null });

    if (Date.now() - lastExam > init.examEveryMs) {
      lastExam = Date.now();
      post({ type: 'exam', exam: await exam(), version });
    }
  }
}

function mean(xs: number[]): number {
  return xs.reduce((s, x) => s + x, 0) / Math.max(1, xs.length);
}

function zScore(xs: number[]): number {
  const m = mean(xs);
  const v = xs.reduce((s, x) => s + (x - m) ** 2, 0) / Math.max(1, xs.length - 1);
  return v > 0 ? m / Math.sqrt(v / xs.length) : 0;
}

main().catch((error: unknown) => post({ type: 'error', error: String(error) }));
