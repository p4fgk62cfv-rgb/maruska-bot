/**
 * The trainable part of the strong bot. A move is scored by how good the hand is after it
 * (a weighted sum over the cards kept) plus a bias for the kind of move. There is one set of
 * weights per stage of the game: early (a big stock), late (the last cards of the stock) and the
 * end (no stock). Self-play training changes these numbers; the code that uses them stays the same.
 */
export interface StageWeights {
  /** Value of a non-trump card per step of rank (0 for the lowest rank … 1 for the ace). */
  card: number;
  /** Flat value of holding a trump. */
  trump: number;
  /** Value of a trump per step of its rank. */
  trumpRank: number;
  /** Per card that has a partner of the same rank in hand (leads well, defends transfers). */
  pair: number;
  /** Per card in hand (negative: fewer cards is better). */
  size: number;
  /** Bias for taking the cards. */
  take: number;
  /** Bias for passing the attack on («Переводной»). */
  transfer: number;
  /** Bias per card thrown in while the defender still beats. */
  throwIn: number;
  /** Bias per card thrown in after the defender said «беру». */
  unload: number;
  /** Bias per extra card led together with the first one. */
  lead: number;
  /** Bias for a move that breaks the rules («С шулерами»). */
  cheat: number;
}

export interface BrainParams {
  early: StageWeights;
  late: StageWeights;
  end: StageWeights;
  /** How often a visibly illegal card of someone else is called out («С шулерами»), 0…1. */
  catchRate: number;
}

export const STAGES = ['early', 'late', 'end'] as const;
export type Stage = (typeof STAGES)[number];
export const WEIGHT_KEYS = ['card', 'trump', 'trumpRank', 'pair', 'size', 'take', 'transfer', 'throwIn', 'unload', 'lead', 'cheat'] as const;

/** A sensible start: roughly the old hard bot's habits. Training moves away from here. */
export const DEFAULT_PARAMS: BrainParams = {
  early: { card: 0.6, trump: 1.2, trumpRank: 0.8, pair: 0.15, size: -0.35, take: -0.6, transfer: 0.3, throwIn: -0.1, unload: 0.15, lead: 0.2, cheat: -0.6 },
  late: { card: 0.5, trump: 1.0, trumpRank: 0.8, pair: 0.15, size: -0.6, take: -0.9, transfer: 0.3, throwIn: 0.0, unload: 0.3, lead: 0.25, cheat: -0.5 },
  end: { card: 0.3, trump: 0.6, trumpRank: 0.6, pair: 0.2, size: -1.2, take: -1.5, transfer: 0.4, throwIn: 0.3, unload: 0.5, lead: 0.4, cheat: -0.4 },
  catchRate: 0.85,
};

export function stageOf(deckCount: number): Stage {
  return deckCount > 6 ? 'early' : deckCount > 0 ? 'late' : 'end';
}

/** A neighbour of `params` for self-play: every weight moves by a normal step of size `sigma` (the catch rate stays). */
export function mutateParams(params: BrainParams, sigma: number, random: () => number): BrainParams {
  const gauss = () => Math.sqrt(-2 * Math.log(1 - random())) * Math.cos(2 * Math.PI * random());
  const next = structuredClone(params);
  for (const stage of STAGES) for (const key of WEIGHT_KEYS) next[stage][key] = round(next[stage][key] + gauss() * sigma);
  return next;
}

/** Params from storage, with anything missing or broken taken from the defaults. */
export function sanitizeParams(raw: unknown): BrainParams {
  const out = structuredClone(DEFAULT_PARAMS);
  if (!raw || typeof raw !== 'object') return out;
  const src = raw as Record<string, Record<string, unknown> | unknown>;
  for (const stage of STAGES) {
    const s = src[stage];
    if (!s || typeof s !== 'object') continue;
    for (const key of WEIGHT_KEYS) {
      const v = (s as Record<string, unknown>)[key];
      if (typeof v === 'number' && Number.isFinite(v) && Math.abs(v) < 50) out[stage][key] = v;
    }
  }
  if (typeof src.catchRate === 'number' && src.catchRate >= 0 && src.catchRate <= 1) out.catchRate = src.catchRate;
  return out;
}

const round = (v: number) => Math.round(v * 1000) / 1000;
