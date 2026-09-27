import { formatStake, GAME_SERVERS, MODE_LABEL_RU, SPEED_LABEL_RU, STAKE_OPTIONS, type MyRoomDto, type RoomSettings } from '@arena/shared';
import { Button, Panel, Toggle } from '@arena/ui';
import { useState } from 'react';
import { ApiError, api } from '../lib/api.js';
import { safeStorage } from '../lib/hooks.js';
import { useNav } from '../navigation.js';
import { useRealtime } from '../realtime.js';
import { useMe } from '../session.js';
import { useToast } from '../toast.js';
import { ScreenHeader } from './common.js';
import { ChipGroup } from './lobbyParts.js';

type Draft = Omit<RoomSettings, 'password'>;
const DRAFT_KEY = 'arena.createDraft';
const DEFAULT: Draft = {
  stake: 100,
  players: 2,
  deckSize: 36,
  speed: 'normal',
  variant: 'podkidnoy',
  throwIn: 'all',
  fairness: 'fair',
  ending: 'classic',
  server: 'almaz',
  isPrivate: false,
};

export default function CreateGameScreen() {
  const me = useMe();
  const { enterRoom } = useRealtime();
  const { back } = useNav();
  const toast = useToast();
  const [draft, setDraft] = useState<Draft>(() => ({ ...DEFAULT, ...safeStorage.get<Partial<Draft>>(DRAFT_KEY, {}) }));
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => ({ ...d, [key]: value }));
  const maxPlayers = draft.deckSize === 24 ? 4 : 6;

  const create = () => {
    setBusy(true);
    safeStorage.set(DRAFT_KEY, draft);
    api<MyRoomDto>('/rooms', { method: 'POST', body: { ...draft, players: Math.min(draft.players, maxPlayers), ...(draft.isPrivate ? { password } : {}) } })
      .then((mine) => {
        back();
        enterRoom(mine);
      })
      .catch((e: unknown) => toast(e instanceof ApiError ? e.message : 'Ошибка', 'error'))
      .finally(() => setBusy(false));
  };

  return (
    <div className="app-stack">
      <ScreenHeader title="Создание игры" />
      <Panel className="app-stack">
        <ChipGroup
          title="Ваша ставка"
          options={STAKE_OPTIONS}
          value={draft.stake}
          render={formatStake}
          disabled={(v) => v > me.wallet.credits}
          onToggle={(v) => set('stake', v)}
        />
        <ChipGroup title="Количество игроков" options={[2, 3, 4, 5, 6] as const} value={draft.players} disabled={(v) => v > maxPlayers} onToggle={(v) => set('players', v)} />
        <ChipGroup title="Колода" options={[24, 36, 52] as const} value={draft.deckSize} render={(v) => `${v} карт`} onToggle={(v) => set('deckSize', v)} />
        <ChipGroup title="Скорость" options={['normal', 'fast'] as const} value={draft.speed} render={(v) => SPEED_LABEL_RU[v]} onToggle={(v) => set('speed', v)} />
        <ChipGroup title="Режим" options={['podkidnoy', 'perevodnoy'] as const} value={draft.variant} render={(v) => MODE_LABEL_RU[v]} onToggle={(v) => set('variant', v)} />
        <ChipGroup title="Подкидывают" options={['all', 'neighbors'] as const} value={draft.throwIn} render={(v) => MODE_LABEL_RU[v]} onToggle={(v) => set('throwIn', v)} />
        <ChipGroup title="Шулеры" options={['fair', 'cheaters'] as const} value={draft.fairness} render={(v) => MODE_LABEL_RU[v]} onToggle={(v) => set('fairness', v)} />
        <ChipGroup title="Концовка" options={['classic', 'draw'] as const} value={draft.ending} render={(v) => MODE_LABEL_RU[v]} onToggle={(v) => set('ending', v)} />
        <label className="app-field">
          <span>Сервер</span>
          <select className="app-input" value={draft.server} onChange={(e) => set('server', e.target.value)}>
            {GAME_SERVERS.map((s) => (
              <option key={s.key} value={s.key}>{s.name}</option>
            ))}
          </select>
        </label>
        <Toggle label="Приватная игра" checked={draft.isPrivate} onChange={(v) => set('isPrivate', v)} />
        {draft.isPrivate && (
          <input className="app-input" type="password" maxLength={32} placeholder="Пароль" value={password} onChange={(e) => setPassword(e.target.value)} />
        )}
      </Panel>
      <Button size="lg" variant="gold" block loading={busy} disabled={draft.isPrivate && !password} onClick={create}>
        Создать игру
      </Button>
    </div>
  );
}
