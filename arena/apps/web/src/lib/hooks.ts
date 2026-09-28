import { useEffect, useState } from 'react';

/** Seconds left until `deadline` (server clock via `now`), refreshed 4× per second. */
export function useCountdown(deadline: number | null, now: () => number = Date.now): number | null {
  const [left, setLeft] = useState<number | null>(null);
  useEffect(() => {
    if (deadline === null) {
      setLeft(null);
      return;
    }
    const tick = () => setLeft(Math.max(0, deadline - now()));
    tick();
    const id = window.setInterval(tick, 250);
    return () => window.clearInterval(id);
  }, [deadline, now]);
  return left;
}

/** localStorage that never throws (private mode, blocked storage, previews). */
export const safeStorage = {
  get<T>(key: string, fallback: T): T {
    try {
      const raw = localStorage.getItem(key);
      return raw ? (JSON.parse(raw) as T) : fallback;
    } catch {
      return fallback;
    }
  },
  set(key: string, value: unknown): void {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* storage unavailable: preference simply is not remembered */
    }
  },
};
