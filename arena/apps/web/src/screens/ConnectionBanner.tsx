import { useEffect, useState } from 'react';
import { useRealtime } from '../realtime.js';

/** Shown only when the trouble lasts: a quick reconnect after a blink passes unnoticed. */
const SHOW_AFTER_MS = 700;
const RESTORED_MS = 1800;

/**
 * The connection state over every screen: «Нет интернета» / «Переподключение…» with the
 * attempt number and a «Повторить» button, then a short «Связь восстановлена».
 * During a game it also says that the game and the stake are safe on the server.
 */
export function ConnectionBanner() {
  const { socket, status, room, game } = useRealtime();
  const [shown, setShown] = useState(false);
  const [restored, setRestored] = useState(false);
  const [, tick] = useState(0);
  const troubled = status === 'reconnecting' || status === 'offline' || (status === 'connecting' && socket.attempt > 0);

  useEffect(() => {
    if (troubled) {
      setRestored(false);
      const id = window.setTimeout(() => setShown(true), SHOW_AFTER_MS);
      return () => window.clearTimeout(id);
    }
    if (status === 'open' && shown) {
      setShown(false);
      setRestored(true);
      const id = window.setTimeout(() => setRestored(false), RESTORED_MS);
      return () => window.clearTimeout(id);
    }
    if (status !== 'open') setShown(false);
    return undefined;
  }, [troubled, status]);

  // The seconds to the next attempt.
  useEffect(() => {
    if (!shown) return;
    const id = window.setInterval(() => tick((n) => n + 1), 500);
    return () => window.clearInterval(id);
  }, [shown]);

  if (restored) {
    return (
      <div className="conn conn--ok" role="status">
        <span className="conn__icon">✓</span>
        <span className="conn__title">Связь восстановлена</span>
      </div>
    );
  }
  if (!shown || !troubled) return null;

  const playing = game?.state.status === 'playing' || room?.status === 'playing';
  const wait = socket.nextRetryAt ? Math.ceil((socket.nextRetryAt - Date.now()) / 1000) : 0;
  const offline = status === 'offline';
  return (
    <div className={`conn${offline ? ' conn--offline' : ''}`} role="alert">
      <span className="conn__spinner" aria-hidden="true" />
      <span className="conn__text">
        <span className="conn__title">{offline ? 'Нет интернета' : socket.restarting ? 'Сервер обновляется…' : 'Переподключение…'}</span>
        <span className="conn__sub">
          {socket.restarting
            ? 'Через несколько секунд всё заработает'
            : playing
              ? 'Партия и ставка сохранены — вернём вас за стол'
              : offline
                ? 'Ждём, когда появится сеть'
                : 'Восстанавливаем связь с сервером'}
          {!offline && socket.attempt > 1 ? ` · попытка ${socket.attempt}` : ''}
        </span>
      </span>
      {(offline || wait > 1) && (
        <button type="button" className="conn__retry" onClick={() => socket.retryNow()}>
          Повторить
        </button>
      )}
    </div>
  );
}
