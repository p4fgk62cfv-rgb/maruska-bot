import type { BrainParams, GameSettings } from '@arena/game-engine';

/** The three practice tables the bots play at all day. */
export const TRAINING_TABLES: { key: string; title: string; settings: GameSettings }[] = [
  { key: 'podkidnoy', title: 'Подкидной, 1 на 1', settings: { variant: 'podkidnoy', throwIn: 'all', fairness: 'fair', ending: 'classic', deckSize: 36, players: 2, speed: 'normal' } },
  { key: 'perevodnoy', title: 'Переводной, 1 на 1', settings: { variant: 'perevodnoy', throwIn: 'all', fairness: 'fair', ending: 'classic', deckSize: 36, players: 2, speed: 'normal' } },
  { key: 'cheaters', title: 'Переводной втроём, с шулерами', settings: { variant: 'perevodnoy', throwIn: 'all', fairness: 'cheaters', ending: 'classic', deckSize: 36, players: 3, speed: 'normal' } },
];

export interface TrainerInit {
  champion: BrainParams;
  version: number;
  sigma?: number;
  duty: number;
  dealsPerGeneration: number;
  examEveryMs: number;
  examGames: number;
  examIterations: number;
}

export interface TrainingExam {
  at: string;
  games: number;
  /** Share of games the new strong bot won against the old «максимальный». */
  winRate: number;
}

export type TrainerMessage =
  | { type: 'generation'; games: number[]; promoted: boolean; version: number; sigma: number; score: number; params: BrainParams | null }
  | { type: 'exam'; exam: TrainingExam; version: number }
  | { type: 'error'; error: string }
  /** The copy now being tried against the champion (the watched tables show these two). */
  | { type: 'challenger'; params: BrainParams; champion: BrainParams; version: number };

/** What the owner sees in «Управление» → «Обучение ботов». */
export interface TrainingStats {
  running: boolean;
  version: number;
  startedAt: string;
  games: number;
  today: { day: string; games: number };
  generations: number;
  improvements: number;
  lastImprovementAt: string | null;
  sigma: number;
  tables: { key: string; title: string; games: number }[];
  exams: (TrainingExam & { version: number })[];
}
