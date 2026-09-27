/**
 * Logical game servers. Today they only group rooms in the lobby; the key is stored
 * on each room so rooms can later be pinned to separate game-server instances.
 */
export interface GameServerInfo {
  key: string;
  name: string;
  /** Gem colour used for the icon. */
  color: string;
  /** Extra rating (percent) for wins on this server. */
  ratingBonus: number;
}

export const GAME_SERVERS: readonly GameServerInfo[] = [
  { key: 'almaz', name: 'Алмаз', color: '#b9f2ff', ratingBonus: 15 },
  { key: 'rubin', name: 'Рубин', color: '#e0115f', ratingBonus: 12 },
  { key: 'sapfir', name: 'Сапфир', color: '#0f52ba', ratingBonus: 12 },
  { key: 'izumrud', name: 'Изумруд', color: '#50c878', ratingBonus: 10 },
  { key: 'ametist', name: 'Аметист', color: '#9966cc', ratingBonus: 10 },
  { key: 'akvamarin', name: 'Аквамарин', color: '#7fffd4', ratingBonus: 8 },
  { key: 'topaz', name: 'Топаз', color: '#ffc87c', ratingBonus: 8 },
  { key: 'opal', name: 'Опал', color: '#a8c3bc', ratingBonus: 6 },
  { key: 'yantar', name: 'Янтарь', color: '#ffbf00', ratingBonus: 6 },
  { key: 'nefrit', name: 'Нефрит', color: '#00a86b', ratingBonus: 5 },
  { key: 'oniks', name: 'Оникс', color: '#5a5a6e', ratingBonus: 5 },
  { key: 'lazurit', name: 'Лазурит', color: '#26619c', ratingBonus: 4 },
  { key: 'zhemchug', name: 'Жемчуг', color: '#eae0c8', ratingBonus: 3 },
  { key: 'aleksandrit', name: 'Александрит', color: '#8e4585', ratingBonus: 3 },
  { key: 'granat', name: 'Гранат', color: '#9b111e', ratingBonus: 2 },
];

export const DEFAULT_SERVER = 'almaz';

export function isServerKey(value: string): boolean {
  return GAME_SERVERS.some((s) => s.key === value);
}
