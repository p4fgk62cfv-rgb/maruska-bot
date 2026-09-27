import type { AuthResponse, MeDto } from '@arena/shared';
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { ApiError, api, setToken, setUnauthorizedHandler } from './lib/api.js';
import { tg } from './lib/telegram.js';

type SessionState =
  | { status: 'loading' }
  | { status: 'outside-telegram' }
  | { status: 'error'; error: ApiError }
  | { status: 'ready'; me: MeDto; startParam: string | null };

interface SessionApi {
  state: SessionState;
  refreshMe: () => Promise<void>;
  retry: () => void;
  devLogin: (id: number, name: string) => Promise<void>;
}

const SessionContext = createContext<SessionApi | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SessionState>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);

  const accept = useCallback((auth: AuthResponse) => {
    setToken(auth.token);
    setState({ status: 'ready', me: auth.me, startParam: auth.startParam });
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => setAttempt((n) => n + 1));
  }, []);

  useEffect(() => {
    if (!tg) {
      setState({ status: 'outside-telegram' });
      return;
    }
    setState({ status: 'loading' });
    // initData is the only identity proof we send; the server verifies its signature.
    api<AuthResponse>('/auth/telegram', { method: 'POST', body: { initData: tg.initData } })
      .then(accept)
      .catch((error: ApiError) => setState({ status: 'error', error }));
  }, [attempt, accept]);

  const refreshMe = useCallback(async () => {
    const me = await api<MeDto>('/me');
    setState((prev) => (prev.status === 'ready' ? { ...prev, me } : prev));
  }, []);

  const devLogin = useCallback(
    async (id: number, name: string) => {
      accept(await api<AuthResponse>('/auth/dev', { method: 'POST', body: { id, name } }));
    },
    [accept],
  );

  return (
    <SessionContext.Provider value={{ state, refreshMe, retry: () => setAttempt((n) => n + 1), devLogin }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionApi {
  const value = useContext(SessionContext);
  if (!value) throw new Error('SessionProvider missing');
  return value;
}

export function useMe(): MeDto {
  const { state } = useSession();
  if (state.status !== 'ready') throw new Error('not signed in');
  return state.me;
}
