import { Icon } from '@arena/ui';
import { useState } from 'react';
import { useInstall } from '../lib/app.js';

/**
 * «Установить Арену»: on Android (and desktop Chrome) a real install button; on iPhone the two
 * steps in Safari. Nothing inside Telegram or when already installed.
 */
export function InstallHint({ compact = false }: { compact?: boolean }) {
  const { mode, install } = useInstall();
  const [open, setOpen] = useState(false);
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
          <strong>Установить на iPhone</strong>
          <small>{open ? 'Два шага в Safari' : 'Значок «Арена» на экране — нажмите, покажу как'}</small>
        </span>
      </button>
      {open && (
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
