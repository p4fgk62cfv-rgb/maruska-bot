import type { PublicUserDto } from './api.js';

/** The Arena's common chat: one room for everyone, outside the games. */
export const CHAT = {
  maxLength: 300,
  /** Messages per page of history. */
  page: 50,
  /** Writing opens after this many finished games (against spam accounts). */
  minGames: 1,
  /** At least this long between two messages of one player… */
  gapMs: 2_000,
  /** …and no more than this many a minute. */
  perMinute: 10,
  /** This many different players reporting a message hide it. */
  reportsToHide: 3,
  /** Older messages are deleted. */
  keepDays: 7,
} as const;

export interface ChatMessageDto {
  id: string;
  user: PublicUserDto;
  text: string;
  createdAt: string;
}

export interface ChatStateDto {
  /** Oldest first. */
  messages: ChatMessageDto[];
  /** Older messages exist (load them with `?before=<first id>`). */
  more: boolean;
  /** Why I cannot write, if I cannot. */
  blocked: { reason: 'games' | 'muted'; until: string | null } | null;
  /** Owners delete messages and take the right to write away. */
  moderator: boolean;
  /** People in the Arena right now. */
  online: number;
}

// ── Profanity: the same rules as the bot's «Антимат» (features/antimat.py) ──

/** Entries: «сука» — the whole word, «хуй*» — words starting with it (prefixes allowed), «*пизд*» — anywhere. */
export const SWEAR_WORDS = [
  'хуй*', 'хуя*', 'хуе*', 'хуё*', 'хули', '*пизд*', 'бля', 'бляд*', 'блять', 'блядь',
  'ебать', 'ебал*', 'ебан*', 'ебну*', 'ебло', 'ебуч*', '*уеб*',
  'сука', 'суки', 'мудак*', 'мудил*', 'пидор*', 'пидар*', 'гандон*', 'шлюх*', 'долбоеб*',
].map((w) => w.replace(/ё/g, 'е'));

const LOOKALIKE: Record<string, string> = {
  a: 'а', b: 'в', c: 'с', e: 'е', h: 'н', k: 'к', m: 'м', o: 'о', p: 'р', t: 'т', x: 'х', y: 'у', u: 'и',
  '3': 'з', '0': 'о', '6': 'б', '@': 'а', $: 'с', ё: 'е',
};

const PREFIXES = [
  '', 'на', 'за', 'вы', 'по', 'у', 'от', 'до', 'об', 'о', 'раз', 'рас', 'при', 'про',
  'пере', 'недо', 'под', 'из', 'вз', 'с', 'съ', 'в', 'долбо', 'ни', 'ах',
];

const WORD = /[а-яёa-z0-9@$]+/giu;
/** Letters split by dots, spaces, stars or dashes: «х.у.й», «х у й». */
const SPACED = /(?<![а-яёa-z])(?:[а-яёa-z][\s.*_-]{1,3}){2,}[а-яёa-z](?![а-яёa-z])/giu;

/** «XYЙ», «хууууй», «xуй» → «хуй». */
export function normalizeWord(word: string): string {
  const mapped = [...word.toLowerCase()].map((ch) => LOOKALIKE[ch] ?? ch).join('');
  return mapped.replace(/[^а-я]/g, '').replace(/(.)\1+/g, '$1');
}

function matches(word: string, entry: string): boolean {
  const head = entry.startsWith('*');
  const tail = entry.endsWith('*');
  const core = entry.replace(/^\*|\*$/g, '');
  if (head && tail) return word.includes(core);
  if (tail) return PREFIXES.some((p) => word.startsWith(p + core));
  if (head) return word.endsWith(core);
  return word === entry;
}

export function isSwear(word: string, words: readonly string[] = SWEAR_WORDS): boolean {
  const norm = normalizeWord(word);
  return norm.length > 0 && words.some((entry) => matches(norm, entry));
}

/** Swear words become «***»; everything else is left as typed. */
export function censor(text: string, words: readonly string[] = SWEAR_WORDS): string {
  const spans: [number, number][] = [];
  for (const m of text.matchAll(SPACED)) if (isSwear(m[0], words)) spans.push([m.index, m.index + m[0].length]);
  for (const m of text.matchAll(WORD)) if (isSwear(m[0], words)) spans.push([m.index, m.index + m[0].length]);
  if (!spans.length) return text;
  spans.sort((a, b) => a[0] - b[0]);
  let out = '';
  let at = 0;
  for (const [start, end] of spans) {
    if (start < at) continue;
    out += `${text.slice(at, start)}***`;
    at = end;
  }
  return out + text.slice(at);
}

/** Links of any kind are not allowed in the chat (spam, phishing). */
export function hasLink(text: string): boolean {
  return /(https?:\/\/|www\.|t\.me\/|telegram\.me\/|\b[a-z0-9-]{2,}\.(ru|com|net|org|io|me|su|рф|xyz|top|info|online|site|app|link|cc|gg)\b)/iu.test(text);
}
