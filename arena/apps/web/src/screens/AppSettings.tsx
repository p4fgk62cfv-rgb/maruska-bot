import { Icon } from '@arena/ui';
import { inTelegram } from '../lib/app.js';
import { tg } from '../lib/telegram.js';
import { useSession } from '../session.js';
import { InstallHint } from './InstallHint.js';

/**
 * In Telegram: «Установить как приложение» opens the Arena in the phone's browser, where it can
 * be installed. In the installed app: install help (if not installed yet) and «Выйти».
 */
export function AppSettings() {
  const { signOut } = useSession();
  if (inTelegram) {
    return (
      <section className="settings__section">
        <h3 className="script-title">Приложение</h3>
        <p className="app-muted">Арену можно поставить на телефон отдельным приложением со значком «Арена» — аккаунт тот же.</p>
        <button type="button" className="settings__outline" onClick={() => tg?.openLink?.(`${location.origin}/?install=1`)}>
          <span>Установить как приложение</span>
          <Icon name="plus" size={28} />
        </button>
      </section>
    );
  }
  return (
    <section className="settings__section">
      <h3 className="script-title">Приложение</h3>
      <InstallHint />
      <button type="button" className="settings__outline" onClick={signOut}>
        <span>Выйти на этом телефоне</span>
        <Icon name="back" size={28} />
      </button>
    </section>
  );
}
