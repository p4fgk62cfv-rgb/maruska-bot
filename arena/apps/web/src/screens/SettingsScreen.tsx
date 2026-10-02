import type { MeDto } from '@arena/shared';
import { Button, Icon, Tabs } from '@arena/ui';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ApiError, api } from '../lib/api.js';
import { settings, useSettings, type Settings, type Theme } from '../lib/settings.js';
import { play, unlockAudio } from '../lib/sound.js';
import { haptic } from '../lib/telegram.js';
import { useMe, useSession } from '../session.js';
import { useToast } from '../toast.js';
import { ScreenHeader } from './common.js';
import { HomeShortcutSetting } from './HomeShortcut.js';
import { HomeBar } from './HomeScreen.js';

const AVATAR_PX = 256;

/** The picture is cropped to a square and shrunk on the phone, so only ~20 KB goes to the server. */
async function squareJpeg(file: File): Promise<string> {
  const bitmap = await createImageBitmap(file);
  const side = Math.min(bitmap.width, bitmap.height);
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = AVATAR_PX;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('canvas');
  ctx.drawImage(bitmap, (bitmap.width - side) / 2, (bitmap.height - side) / 2, side, side, 0, 0, AVATAR_PX, AVATAR_PX);
  bitmap.close();
  return canvas.toDataURL('image/jpeg', 0.85);
}

export default function SettingsScreen() {
  const me = useMe();
  const s = useSettings();
  const { refreshMe } = useSession();
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState(me.name);
  const [busy, setBusy] = useState<null | 'name' | 'avatar'>(null);
  useEffect(() => setName(me.name), [me.name]);

  const fail = (e: unknown) => toast(e instanceof ApiError ? (e.code === 'VALIDATION_FAILED' ? 'Такое имя нельзя: 2–20 символов, без «админ» и «Маруська»' : e.message) : 'Не получилось', 'error');

  const saveName = async () => {
    const next = name.replace(/\s+/g, ' ').trim();
    if (next === me.name) return;
    setBusy('name');
    try {
      // Clearing the field brings the Telegram name back.
      await api<MeDto>('/me/nickname', { method: 'PUT', body: { nickname: next === me.telegramName ? '' : next } });
      await refreshMe();
      toast(next ? 'Имя сохранено' : 'Вернули имя из Telegram', 'success');
    } catch (e) {
      fail(e);
      setName(me.name);
    } finally {
      setBusy(null);
    }
  };

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy('avatar');
    try {
      const image = await squareJpeg(file);
      await api<MeDto>('/me/avatar', { method: 'POST', body: { image } });
      await refreshMe();
      toast('Аватарка обновлена', 'success');
    } catch (e) {
      fail(e);
    } finally {
      setBusy(null);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const resetAvatar = async () => {
    setBusy('avatar');
    try {
      await api<MeDto>('/me/avatar', { method: 'DELETE' });
      await refreshMe();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(null);
    }
  };

  const copyId = () =>
    void navigator.clipboard?.writeText(me.id).then(
      () => toast('ID скопирован', 'success'),
      () => toast(me.id),
    );

  const flag = (key: keyof Settings, label: string, after?: (on: boolean) => void): ReactNode => (
    <Check
      key={key}
      label={label}
      checked={Boolean(s[key])}
      onChange={(on) => {
        settings.set({ [key]: on } as Partial<Settings>);
        after?.(on);
      }}
    />
  );

  return (
    <div className="app-stack settings">
      <ScreenHeader title="Настройки" />
      <div className="settings__bar">
        <HomeBar />
      </div>

      <form
        className="settings__name"
        onSubmit={(e) => {
          e.preventDefault();
          (document.activeElement as HTMLElement | null)?.blur();
        }}
      >
        <input
          aria-label="Имя в игре"
          maxLength={20}
          value={name}
          placeholder={me.telegramName}
          onChange={(e) => setName(e.target.value)}
          onBlur={() => void saveName()}
          disabled={busy === 'name'}
        />
        <Icon name="settings" size={18} aria-hidden="true" />
      </form>

      <input ref={fileRef} type="file" accept="image/*" hidden onChange={(e) => void upload(e.target.files?.[0])} />
      <button type="button" className="settings__outline" disabled={busy === 'avatar'} onClick={() => fileRef.current?.click()}>
        <span>{busy === 'avatar' ? 'Загружаем…' : 'Загрузить аватарку'}</span>
        <Icon name="camera" size={28} />
      </button>
      {me.customAvatar && (
        <Button variant="ghost" block disabled={busy === 'avatar'} onClick={() => void resetAvatar()}>
          Вернуть фото из Telegram
        </Button>
      )}

      <HomeShortcutSetting />

      <section className="settings__section">
        <h3 className="script-title">Тема</h3>
        <Tabs<Theme>
          value={s.theme}
          onChange={(theme) => settings.set({ theme })}
          items={[
            { value: 'light', label: 'светлая' },
            { value: 'dark', label: 'тёмная' },
            { value: 'system', label: 'системная' },
          ]}
        />
      </section>

      <section className="settings__section">
        <h3 className="script-title">Дизайн игры</h3>
        <Tabs<'classic' | 'daylight'>
          value={s.homeDesign}
          onChange={(homeDesign) => settings.set({ homeDesign })}
          items={[
            { value: 'classic', label: 'старый' },
            { value: 'daylight', label: 'светлый' },
          ]}
        />
        <p className="app-muted" style={{ textAlign: 'center', marginTop: 8 }}>
          Старый дизайн используется по умолчанию. Светлый стиль меняет оформление всех экранов. Выбор сохраняется на устройстве.
        </p>
      </section>

      <div className="settings__checks">
        {flag('sound', 'Включить звуки', (on) => {
          unlockAudio();
          if (on) play('card');
        })}
        {s.sound && (
          <label className="settings__volume">
            <span>Громкость</span>
            <input
              type="range"
              min={0.1}
              max={1}
              step={0.05}
              value={s.volume}
              onChange={(e) => settings.set({ volume: Number(e.target.value) })}
              onPointerUp={() => play('card')}
              aria-label="Громкость"
            />
          </label>
        )}
        {flag('vibration', 'Включить вибрации', (on) => on && haptic.tap())}
        {flag('actionRight', 'Кнопка действия справа')}
        <Check label="Сортировка карт по значению" checked={s.handSort === 'rank'} onChange={(on) => settings.set({ handSort: on ? 'rank' : 'suit' })} />
        {flag('sortDesc', 'Развернуть сортировку карт')}
        {flag('doubleTap', 'Действие по двойному тапу')}
        {flag('animations', 'Анимации карт')}
        {flag('emojis', 'Включить смайлы')}
        {flag('rewardAnimations', 'Включить анимации наград')}
      </div>

      <p className="settings__meta">
        Ваш ID: <strong>{me.id.slice(0, 8).toUpperCase()}</strong>
        <button type="button" className="settings__copy" onClick={copyId}>
          <Icon name="copy" size={18} /> копировать
        </button>
      </p>
      <p className="settings__meta">версия приложения: {__APP_VERSION__}</p>
    </div>
  );
}

/** Big square tick box with a label, like a paper form. */
function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: (on: boolean) => void }) {
  return (
    <label className={`check${checked ? ' check--on' : ''}`}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="check__box" aria-hidden="true" />
      <span>{label}</span>
    </label>
  );
}
