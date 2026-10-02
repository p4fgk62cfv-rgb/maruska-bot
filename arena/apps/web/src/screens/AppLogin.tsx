import type { AuthResponse } from '@arena/shared';
import { Button, Icon } from '@arena/ui';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, api } from '../lib/api.js';
import { deviceName } from '../lib/app.js';
import { useSession } from '../session.js';
import { InstallHint } from './InstallHint.js';

interface LoginRequest {
  id: string;
  secret: string;
  link: string;
  expiresAt: number;
}

const POLL_MS = 2000;

/**
 * Sign-in for the installed app: «Войти через Telegram» opens the chat with Мара, who asks
 * «Войти в Арену на этом устройстве?»; after «Войти» the app (polling with its secret) is in.
 */
export function AppLogin({ dev }: { dev?: React.ReactNode }) {
  const { signIn } = useSession();
  const [request, setRequest] = useState<LoginRequest | null>(null);
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const busy = useRef(false);

  // The link is ready before the tap: opening Telegram must happen right in the tap.
  const prepare = useCallback(() => {
    setError(null);
    api<LoginRequest>('/auth/app/start', { method: 'POST', body: { device: deviceName() } })
      .then(setRequest)
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : 'Нет соединения с сервером'));
  }, []);
  useEffect(prepare, [prepare]);

  // An unused link expires after a few minutes: get a fresh one.
  useEffect(() => {
    if (!request || waiting) return;
    const id = window.setTimeout(prepare, Math.max(10_000, request.expiresAt - Date.now() - 20_000));
    return () => window.clearTimeout(id);
  }, [request, waiting, prepare]);

  const poll = useCallback(async () => {
    if (!request || busy.current) return;
    busy.current = true;
    try {
      const res = await api<{ status: 'pending' } | ({ status: 'done' } & AuthResponse)>('/auth/app/poll', { method: 'POST', body: { id: request.id, secret: request.secret } });
      if (res.status === 'done') signIn(res);
    } catch (e) {
      if (e instanceof ApiError && e.code === 'NOT_FOUND') {
        setWaiting(false);
        setError('Время на подтверждение вышло — нажмите «Войти через Telegram» ещё раз.');
        prepare();
      }
    } finally {
      busy.current = false;
    }
  }, [request, signIn, prepare]);

  // While waiting: ask every couple of seconds and right when the app comes back from Telegram.
  useEffect(() => {
    if (!waiting) return;
    const id = window.setInterval(() => document.visibilityState === 'visible' && void poll(), POLL_MS);
    const back = () => document.visibilityState === 'visible' && void poll();
    document.addEventListener('visibilitychange', back);
    window.addEventListener('focus', back);
    return () => {
      window.clearInterval(id);
      document.removeEventListener('visibilitychange', back);
      window.removeEventListener('focus', back);
    };
  }, [waiting, poll]);

  return (
    <div className="app-login">
      <img className="app-login__logo" src="/icons/icon-512.png" alt="" width={112} height={112} />
      <h1 className="app-login__title">Маруська Арена</h1>
      <p className="app-login__sub">Дурак онлайн: подкидной и переводной, турниры, друзья</p>

      {waiting ? (
        <div className="app-login__wait">
          <span className="ui-spinner" aria-hidden="true" />
          <strong>Подтвердите вход в Telegram</strong>
          <span>В чате с Марой нажмите «✅ Войти в Арену» и вернитесь сюда — игра откроется сама.</span>
          {request && (
            <a className="app-login__again" href={request.link} target="_blank" rel="noreferrer">
              Открыть Telegram ещё раз
            </a>
          )}
        </div>
      ) : (
        <a
          className={`app-login__tg${request ? '' : ' app-login__tg--off'}`}
          href={request?.link ?? '#'}
          target="_blank"
          rel="noreferrer"
          onClick={(e) => {
            if (!request) e.preventDefault();
            else setWaiting(true);
          }}
        >
          <Icon name="send" size={22} />
          Войти через Telegram
        </a>
      )}
      {error && <p className="app-login__error">{error}</p>}
      {!request && !error && <Button variant="ghost" size="sm" loading>Готовим вход…</Button>}

      <p className="app-login__note">Аккаунт тот же, что в Telegram: баланс, рейтинг и друзья сохранятся.</p>
      <InstallHint />
      {dev}
    </div>
  );
}
