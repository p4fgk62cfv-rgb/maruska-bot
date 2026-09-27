/** XP needed to go from `level` to `level + 1`. Grows linearly: 100, 200, 300… */
export function xpForLevel(level: number): number {
  return level * 100;
}

export function levelFromXp(xp: number): { level: number; intoLevel: number; toNext: number } {
  let level = 1;
  let remaining = xp;
  while (remaining >= xpForLevel(level)) {
    remaining -= xpForLevel(level);
    level++;
  }
  return { level, intoLevel: remaining, toNext: xpForLevel(level) - remaining };
}
