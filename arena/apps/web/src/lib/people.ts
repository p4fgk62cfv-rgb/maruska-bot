import { MODE_LABEL_RU, type Presence } from '@arena/shared';

export const PRESENCE_TEXT: Record<Presence, string> = { online: 'в сети', in_game: 'в игре', offline: 'не в сети' };

const TIME = new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit' });
const DATE = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long' });
const DATE_YEAR = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
const SHORT = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short' });

const dayStart = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();

/** Like Telegram: «был(а) сегодня в 20:41», «вчера в 9:05», «28 сентября в 21:10», «только что». */
export function lastSeenText(iso: string, now = new Date()): string {
  const at = new Date(iso);
  const minutes = Math.floor((now.getTime() - at.getTime()) / 60_000);
  if (minutes < 2) return 'был(а) только что';
  if (minutes < 60) return `был(а) ${minutes} мин назад`;
  const days = Math.round((dayStart(now) - dayStart(at)) / 86_400_000);
  const time = TIME.format(at);
  if (days === 0) return `был(а) сегодня в ${time}`;
  if (days === 1) return `был(а) вчера в ${time}`;
  return `был(а) ${(at.getFullYear() === now.getFullYear() ? DATE : DATE_YEAR).format(at)} в ${time}`;
}

export function presenceText(presence: Presence, lastSeenAt: string | null): string {
  return presence === 'offline' && lastSeenAt ? lastSeenText(lastSeenAt) : PRESENCE_TEXT[presence];
}

/** «сегодня, 20:41», «вчера, 9:05», «28 сент.» — for match history. */
export function whenText(iso: string, now = new Date()): string {
  const at = new Date(iso);
  const days = Math.round((dayStart(now) - dayStart(at)) / 86_400_000);
  if (days === 0) return `сегодня, ${TIME.format(at)}`;
  if (days === 1) return `вчера, ${TIME.format(at)}`;
  return SHORT.format(at);
}

export function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

/** «Подкидной · 36 карт · 1 на 1». */
export function modeText(mode: { variant: string; deckSize: number; players: number }): string {
  const table = mode.players === 2 ? '1 на 1' : `${mode.players} ${plural(mode.players, 'игрок', 'игрока', 'игроков')}`;
  return `${MODE_LABEL_RU[mode.variant] ?? mode.variant} · ${mode.deckSize} карт · ${table}`;
}
