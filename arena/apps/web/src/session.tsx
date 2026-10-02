import type { AuthResponse, MeDto } from '@arena/shared';
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { ApiError, api, getToken, setToken, setUnauthorizedHandler } from './lib/api.js';
import { tg } from './lib/telegram.js';
import { savedSession } from './lib/app.js';

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
  /** New token for the current session; false when it cannot be renewed (banned, too old). */
  renew: () => Promise<boolean>;
  /** The installed app: a session confirmed in the bot. */
  signIn: (auth: AuthResponse) => void;
  /** The installed app: forget the session on this phone. */
  signOut: () => void;
}

/** Renew the session when less than this is left (the app checks on a timer and on coming back). */
const RENEW_BEFORE_MS = 12 * 3600_000;

const SessionContext = createContext<SessionApi | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SessionState>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const expiresAt = useRef(0);

  const accept = useCallback((auth: AuthResponse) => {
    setToken(auth.token);
    expiresAt.current = auth.expiresAt;
    // Outside Telegram nothing proves who you are on the next launch: remember the session.
    if (!tg) savedSession.set({ token: auth.token, expiresAt: auth.expiresAt });
    setState({ status: 'ready', me: auth.me, startParam: auth.startParam });
  }, []);


  useEffect(() => {
    if (!tg) {
      // The installed app: come back with the remembered session (renewed if it is old).
      const saved = savedSession.get();
      if (!saved) {
        setState({ status: 'outside-telegram' });
        return;
      }
      setToken(saved.token);
      expiresAt.current = saved.expiresAt;
      setState({ status: 'loading' });
      void (async () => {
        if (saved.expiresAt - Date.now() < RENEW_BEFORE_MS && !(await renewRef.current())) throw new ApiError('UNAUTHORIZED', '', 401);
        const me = await api<MeDto>('/me');
        setState({ status: 'ready', me, startParam: new URLSearchParams(location.search).get('start') });
      })().catch((error: unknown) => {
        if (error instanceof ApiError && (error.code === 'UNAUTHORIZED' || error.code === 'BANNED')) {
          savedSession.clear();
          setToken(null);
          setState({ status: 'outside-telegram' });
        } else setState({ status: 'error', error: error instanceof ApiError ? error : new ApiError('NO_CONNECTION', 'Нет соединения', 0) });
      });
      return;
    }
    setState({ status: 'loading' });
    // initData is the only identity proof we send; the server verifies its signature.
    api<AuthResponse>('/auth/telegram', { method: 'POST', body: { initData: tg.initData } })
      .then(accept)
      .catch((error: ApiError) => setState({ status: 'error', error }));
  }, [attempt, accept]);

  const renewing = useRef<Promise<boolean> | null>(null);
  const renew = useCallback((): Promise<boolean> => {
    // One renewal at a time: the timer, the socket and «back to the app» may ask together.
    renewing.current ??= fetch('/api/auth/refresh', { method: 'POST', headers: { authorization: `Bearer ${getToken() ?? ''}` } })
      .then(async (res) => {
        if (!res.ok) return false;
        const next = (await res.json()) as { token: string; expiresAt: number };
        setToken(next.token);
        expiresAt.current = next.expiresAt;
        if (!tg) savedSession.set(next);
        return true;
      })
      .catch(() => false)
      .finally(() => {
        renewing.current = null;
      });
    return renewing.current;
  }, []);

  const renewRef = useRef(renew);
  renewRef.current = renew;

  // A 401 means the session ran out: renew it quietly; sign in again only if that fails.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      void renew().then((ok) => {
        if (!ok) setAttempt((n) => n + 1);
      });
    });
  }, [renew]);

  // A Mini App may stay open (or minimised) for days, longer than one session and far longer
  // than Telegram's initData is accepted: keep the session fresh while it lives.
  useEffect(() => {
    if (state.status !== 'ready') return;
    const check = () => {
      if (document.visibilityState === 'visible' && expiresAt.current - Date.now() < RENEW_BEFORE_MS) void renew();
    };
    const id = window.setInterval(check, 15 * 60_000);
    document.addEventListener('visibilitychange', check);
    check();
    return () => {
      window.clearInterval(id);
      document.removeEventListener('visibilitychange', check);
    };
  }, [state.status, renew]);

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
    <SessionContext.Provider
      value={{
        state,
        refreshMe,
        retry: () => setAttempt((n) => n + 1),
        devLogin,
        renew,
        signIn: accept,
        signOut: () => {
          savedSession.clear();
          setToken(null);
          setState({ status: 'outside-telegram' });
        },
      }}
    >
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
