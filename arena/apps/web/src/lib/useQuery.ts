import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, api } from './api.js';

export interface Query<T> {
  data: T | undefined;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
}

const cache = new Map<string, unknown>();

/** Minimal stale-while-revalidate GET: cached data renders instantly, a fresh copy replaces it. */
export function useQuery<T>(path: string | null): Query<T> {
  const [data, setData] = useState<T | undefined>(() => (path ? (cache.get(path) as T | undefined) : undefined));
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const seq = useRef(0);

  const load = useCallback(() => {
    if (!path) return;
    const id = ++seq.current;
    setLoading(true);
    api<T>(path)
      .then((value) => {
        if (id !== seq.current) return;
        cache.set(path, value);
        setData(value);
        setError(null);
      })
      .catch((e: unknown) => id === seq.current && setError(e instanceof ApiError ? e : new ApiError('SERVER_ERROR', 'Ошибка', 500)))
      .finally(() => id === seq.current && setLoading(false));
  }, [path]);

  useEffect(load, [load]);
  return { data, error, loading, reload: load };
}

export function primeCache(path: string, value: unknown): void {
  cache.set(path, value);
}
