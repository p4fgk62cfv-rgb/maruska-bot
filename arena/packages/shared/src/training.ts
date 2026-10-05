import type { CardId } from '@arena/game-engine';

/** One seat at a bot training table, watched with open cards. */
export interface TrainingSeatDto {
  id: string;
  name: string;
  /** The current best bot, or the changed copy being tried against it. */
  role: 'champion' | 'challenger';
  hand: CardId[];
  status: 'active' | 'out' | 'left';
  attacker: boolean;
  defender: boolean;
}

/** A training table as spectators see it: every hand open, one move a second. */
export interface TrainingTableDto {
  key: string;
  title: string;
  /** Game number at this table since the server started. */
  game: number;
  score: { champion: number; challenger: number };
  championVersion: number;
  seats: TrainingSeatDto[];
  table: { attack: CardId; defense: CardId | null }[];
  trump: { card: CardId; inStock: boolean };
  deck: number;
  discard: number;
  /** The last move in words: «Чемпион переводит 9♠». */
  last: string | null;
  /** When the game is over: who is the fool. */
  result: string | null;
}
