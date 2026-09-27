import { Panel, Tabs, Toggle } from '@arena/ui';
import { settings, useSettings } from '../lib/settings.js';
import { play, unlockAudio } from '../lib/sound.js';
import { haptic } from '../lib/telegram.js';
import { ScreenHeader } from './common.js';

export default function SettingsScreen() {
  const s = useSettings();
  return (
    <div className="app-stack">
      <ScreenHeader title="Настройки" subtitle="Сохраняются на этом устройстве" />
      <Panel className="app-stack">
        <Toggle
          label="Звук"
          checked={s.sound}
          onChange={(v) => {
            settings.set({ sound: v });
            unlockAudio();
            if (v) play('card');
          }}
        />
        <Toggle
          label="Вибрация"
          checked={s.vibration}
          onChange={(v) => {
            settings.set({ vibration: v });
            if (v) haptic.tap();
          }}
        />
        <Toggle label="Анимации карт" checked={s.animations} onChange={(v) => settings.set({ animations: v })} />
      </Panel>
      <Panel className="app-stack">
        <strong>Сортировка карт в руке</strong>
        <Tabs
          value={s.handSort}
          onChange={(v) => settings.set({ handSort: v })}
          items={[
            { value: 'suit', label: 'По мастям' },
            { value: 'rank', label: 'По старшинству' },
          ]}
        />
        <p className="app-muted">Во время игры можно переключать свайпом вправо по руке.</p>
      </Panel>
    </div>
  );
}
