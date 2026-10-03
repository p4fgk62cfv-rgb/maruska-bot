import { Icon } from '@arena/ui';
import { useState } from 'react';
import { inTelegram, openInstallPage } from '../lib/app.js';
import { safeStorage } from '../lib/hooks.js';
import { tg } from '../lib/telegram.js';
import { InstallHint } from './InstallHint.js';

const HIDDEN_KEY = 'arena.installCardHidden';

/**
 * Home screen: «Установить приложение». In Telegram it opens the Arena in the phone's browser,
 * where it installs as «Арена»; outside Telegram it is the install button / iPhone steps.
 */
export function InstallCard() {
  const [hidden, setHidden] = useState(() => safeStorage.get<boolean>(HIDDEN_KEY, false));
  if (!inTelegram) return <InstallHint compact />;
  if (hidden || !tg?.openLink) return null;
  return (
    <div className="home-shortcut">
      <button type="button" className="home-shortcut__main" onClick={openInstallPage}>
        <img className="home-shortcut__img" src="/icons/icon-192.png" alt="" width={38} height={38} />
        <span className="home-shortcut__text">
          <strong>Установить приложение «Арена»</strong>
          <small>Значок на экране телефона — играйте без Telegram</small>
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
