import { Icon } from '@arena/ui';
import { useEffect, useRef, useState } from 'react';
import { safeStorage } from '../lib/hooks.js';
import { canAddToHomeScreen, useHomeScreen } from '../lib/homeScreen.js';
import { useToast } from '../toast.js';

const HIDDEN_KEY = 'arena.homeShortcutHidden';

/** Says «готово» once the icon really appears on the home screen. */
function useAddedToast(status: ReturnType<typeof useHomeScreen>['status']) {
  const toast = useToast();
  const was = useRef(status);
  useEffect(() => {
    if (status === 'added' && was.current && was.current !== 'added') toast('Значок Арены на главном экране — открывайте игру одним касанием', 'success');
    was.current = status;
  }, [status, toast]);
}

/** Home screen card: «Добавить Арену на главный экран» (can be hidden with ×). */
export function HomeShortcutCard() {
  const { status, add } = useHomeScreen();
  const [hidden, setHidden] = useState(() => safeStorage.get<boolean>(HIDDEN_KEY, false));
  useAddedToast(status);
  if (hidden || !canAddToHomeScreen(status)) return null;
  return (
    <div className="home-shortcut">
      <button type="button" className="home-shortcut__main" onClick={add}>
        <span className="home-shortcut__icon">
          <Icon name="plus" size={20} />
        </span>
        <span className="home-shortcut__text">
          <strong>Арена на главный экран</strong>
          <small>Значок на телефоне — игра открывается одним касанием</small>
        </span>
      </button>
      <button
        type="button"
        className="home-shortcut__close"
        aria-label="Скрыть"
        onClick={() => {
          safeStorage.set(HIDDEN_KEY, true);
          setHidden(true);
        }}
      >
        <Icon name="close" size={16} />
      </button>
    </div>
  );
}

/** Settings row: always there while Telegram can add the icon. */
export function HomeShortcutSetting() {
  const { status, add } = useHomeScreen();
  useAddedToast(status);
  if (status === null || status === 'unsupported') return null;
  return (
    <section className="settings__section">
      <h3 className="script-title">Значок на телефоне</h3>
      {status === 'added' ? (
        <p className="app-muted">Значок Арены уже на главном экране.</p>
      ) : (
        <button type="button" className="settings__outline" onClick={add}>
          <span>Добавить на главный экран</span>
          <Icon name="plus" size={28} />
        </button>
      )}
    </section>
  );
}
