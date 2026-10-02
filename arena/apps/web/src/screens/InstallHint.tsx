import { Icon } from '@arena/ui';
import { useState } from 'react';
import { androidBrowserLink, useInstall } from '../lib/app.js';

/**
 * «Установить Арену»: on Android (and desktop Chrome) a real install button; on iPhone the two
 * steps in Safari. Nothing inside Telegram or when already installed.
 */
export function InstallHint({ compact = false }: { compact?: boolean }) {
  const { mode, install } = useInstall();
  // Came here from «Установить приложение» in Telegram, or on Android without the browser's own
  // prompt (often Telegram's built-in browser, which cannot install): show the steps at once.
  const [open, setOpen] = useState(() => new URLSearchParams(location.search).has('install') || mode === 'android');
  if (!mode) return null;
  if (mode === 'prompt') {
    return (
      <button type="button" className={`install-hint${compact ? ' install-hint--compact' : ''}`} onClick={() => void install()}>
        <img src="/icons/icon-192.png" alt="" width={36} height={36} />
        <span>
          <strong>Установить приложение</strong>
          <small>Значок «Арена» на экране телефона</small>
        </span>
      </button>
    );
  }
  return (
    <div className={`install-hint install-hint--ios${compact ? ' install-hint--compact' : ''}`}>
      <button type="button" className="install-hint__head" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <img src="/icons/icon-192.png" alt="" width={36} height={36} />
        <span>
          <strong>{mode === 'ios' ? 'Установить на iPhone' : 'Установить на телефон'}</strong>
          <small>{open ? 'Два шага в браузере' : 'Значок «Арена» на экране — нажмите, покажу как'}</small>
        </span>
      </button>
      {open && mode === 'android' && (
        <>
          <a className="install-hint__browser" href={androidBrowserLink()}>
            Открыть в Chrome
          </a>
          <ol className="install-hint__steps">
            <li>
              Если страница открыта внутри Telegram: нажмите ⋮ вверху справа → «Открыть в Samsung Browser» (или «в Chrome»)
            </li>
            <li>В браузере: ⋮ → «Установить приложение» или «Добавить на главный экран»</li>
            <li>Откройте Арену значком «Арена» на экране телефона</li>
          </ol>
        </>
      )}
      {open && mode === 'ios' && (
        <ol className="install-hint__steps">
          <li>
            Внизу Safari нажмите «Поделиться» <Icon name="share" size={18} />
          </li>
          <li>
            Выберите «На экран „Домой“» <Icon name="plus" size={18} /> и нажмите «Добавить»
          </li>
          <li>Откройте Арену значком на экране — она запустится на весь экран</li>
        </ol>
      )}
    </div>
  );
}
