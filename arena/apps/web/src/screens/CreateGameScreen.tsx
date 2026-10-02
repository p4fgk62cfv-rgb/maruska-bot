import { GAME_SERVERS, MODE_LABEL_RU, MODE_PAIRS, STAKE_OPTIONS, type GameMode, type MyRoomDto, type RoomSettings } from '@arena/shared';
import { Button, CurrencyIcon, Icon } from '@arena/ui';
import { useState } from 'react';
import { ApiError, api } from '../lib/api.js';
import { safeStorage } from '../lib/hooks.js';
import { useRealtime } from '../realtime.js';
import { useMe } from '../session.js';
import { useToast } from '../toast.js';
import { ScreenHeader } from './common.js';
import { MODE_ICON, ScriptTitle, Segmented, StakeSlider } from './lobbyParts.js';

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
  bots: false,
  botLevel: 'normal',
};
const PAIR_KEY = ['variant', 'throwIn', 'fairness', 'ending'] as const;
type BotLevel = NonNullable<Draft['botLevel']>;
const BOT_LEVELS: { value: BotLevel; label: string; hint: string }[] = [
  { value: 'easy', label: 'Минимальный', hint: 'Часто ошибается — для разминки' },
  { value: 'normal', label: 'Средний', hint: 'Играет как обычный игрок, иногда промахивается' },
  { value: 'hard', label: 'Максимальный', hint: 'Без ошибок: бережёт козыри, считает вышедшие карты, точно доигрывает концовку' },
];

const randomPin = () => String(1000 + Math.floor(Math.random() * 9000));

export default function CreateGameScreen() {
  const me = useMe();
  const { enterRoom } = useRealtime();
  const toast = useToast();
  const [draft, setDraft] = useState<Draft>(() => {
    const saved = { ...DEFAULT, ...safeStorage.get<Partial<Draft>>(DRAFT_KEY, {}) };
    // A stake from the old ladder or above the balance falls back to the nearest affordable one.
    const affordable = STAKE_OPTIONS.filter((s) => s <= Math.max(me.wallet.credits, STAKE_OPTIONS[0]));
    return { ...saved, stake: affordable.includes(saved.stake as never) ? saved.stake : affordable[affordable.length - 1]! };
  });
  const [password, setPassword] = useState(randomPin);
  const [editingPin, setEditingPin] = useState(false);
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => ({ ...d, [key]: value }));
  const maxPlayers = draft.deckSize === 24 ? 4 : 6;

  const create = () => {
    setBusy(true);
    safeStorage.set(DRAFT_KEY, draft);
    api<MyRoomDto>('/rooms', { method: 'POST', body: { ...draft, players: Math.min(draft.players, maxPlayers), bots: Boolean(draft.bots), botLevel: draft.bots ? draft.botLevel : undefined, ...(draft.isPrivate ? { password } : {}) } })
      .then(enterRoom)
      .catch((e: unknown) => toast(e instanceof ApiError ? e.message : 'Ошибка', 'error'))
      .finally(() => setBusy(false));
  };

  return (
    <div className="app-stack felt-form">
      <ScreenHeader title="Создание игры" />

      <section className="felt-section">
        <div className="stake-head">
          <ScriptTitle>Ваша ставка:</ScriptTitle>
          <span className="stake-head__value">
            {draft.stake.toLocaleString('ru-RU')} <CurrencyIcon kind="credits" size={24} />
          </span>
        </div>
        <StakeSlider value={draft.stake} max={me.wallet.credits} onChange={(v) => set('stake', v)} />
      </section>

      <section className="felt-section">
        <ScriptTitle>Игроки</ScriptTitle>
        <Segmented label="Игроки" options={[2, 3, 4, 5, 6] as const} value={Math.min(draft.players, maxPlayers)} disabled={(v) => v > maxPlayers} onToggle={(v) => set('players', v)} />
      </section>

      <div className="felt-pair">
        <section className="felt-section">
          <ScriptTitle>Колода</ScriptTitle>
          <Segmented label="Колода" options={[24, 36, 52] as const} value={draft.deckSize} onToggle={(v) => set('deckSize', v)} />
        </section>
        <section className="felt-section">
          <ScriptTitle>Скорость</ScriptTitle>
          <Segmented
            label="Скорость"
            options={['normal', 'fast'] as const}
            value={draft.speed}
            render={(v) => <Icon name={v === 'fast' ? 'speedFast' : 'speedNormal'} size={20} aria-label={v === 'fast' ? 'Быстрая' : 'Обычная'} />}
            onToggle={(v) => set('speed', v)}
          />
        </section>
      </div>

      <section className="felt-section">
        <ScriptTitle>Режимы игры</ScriptTitle>
        <div className="pair-grid">
          {MODE_PAIRS.map((pair, i) => {
            const key = PAIR_KEY[i]!;
            return (
              <div key={key} className="pair-card" role="radiogroup" aria-label={pair.map((m) => MODE_LABEL_RU[m]).join(' или ')}>
                {pair.map((mode: GameMode) => {
                  const on = draft[key] === mode;
                  return (
                    <button
                      key={mode}
                      type="button"
                      role="radio"
                      aria-checked={on}
                      className={`pair-card__half${on ? ' pair-card__half--on' : ''}`}
                      onClick={() => setDraft((d) => ({ ...d, [key]: mode }))}
                    >
                      <Icon name={MODE_ICON[mode]} size={30} />
                      <span>{MODE_LABEL_RU[mode]}</span>
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>
      </section>

      <section className="felt-section bots-pick">
        <label className={`pin${draft.bots ? ' pin--on' : ''}`}>
          <input type="checkbox" checked={Boolean(draft.bots)} onChange={(e) => set('bots', e.target.checked)} />
          <span className="pin__box" aria-hidden="true" />
          <span className="bots-pick__title">Добавить ботов</span>
        </label>
        <span className="bots-pick__hint">
          {draft.bots ? 'Если никто не придёт, свободные места займут боты' : 'Стол ждёт только живых игроков'}
        </span>
        {draft.bots && (
          <div className="bots-pick__levels" role="radiogroup" aria-label="Уровень ботов">
            {BOT_LEVELS.map((l) => (
              <button
                key={l.value}
                type="button"
                role="radio"
                aria-checked={(draft.botLevel ?? 'normal') === l.value}
                className={`bots-pick__level${(draft.botLevel ?? 'normal') === l.value ? ' bots-pick__level--on' : ''}`}
                onClick={() => set('botLevel', l.value)}
              >
                <strong>{l.label}</strong>
                <span>{l.hint}</span>
              </button>
            ))}
          </div>
        )}
      </section>

      <label className="felt-server">
        <span>Сервер</span>
        <select value={draft.server} onChange={(e) => set('server', e.target.value)}>
          {GAME_SERVERS.map((s) => (
            <option key={s.key} value={s.key}>
              {s.name}
            </option>
          ))}
        </select>
      </label>

      <div className="create-foot">
        <label className={`pin${draft.isPrivate ? ' pin--on' : ''}`}>
          <input
            type="checkbox"
            checked={draft.isPrivate}
            onChange={(e) => {
              set('isPrivate', e.target.checked);
              if (e.target.checked) setEditingPin(true);
            }}
          />
          <span className="pin__box" aria-hidden="true" />
          <span className="pin__label">Пароль:</span>
          {draft.isPrivate ? (
            // Typing happens in a dialog at the top: down here the keyboard would cover the field.
            <button
              type="button"
              className="pin__input pin__input--button"
              aria-label="Изменить пароль"
              onClick={(e) => {
                e.preventDefault();
                setEditingPin(true);
              }}
            >
              {password || '····'}
            </button>
          ) : (
            <span className="pin__off">нет</span>
          )}
        </label>
        <Button size="lg" variant="gold" icon="play" loading={busy} disabled={draft.isPrivate && !password} onClick={create}>
          Создать
        </Button>
      </div>
      {editingPin && <PinDialog value={password} onDone={(v) => (setPassword(v), setEditingPin(false))} />}
    </div>
  );
}

/** PIN entry near the top of the screen, above the phone keyboard, with large digits. */
function PinDialog({ value, onDone }: { value: string; onDone: (value: string) => void }) {
  const [draft, setDraft] = useState(value);
  const done = () => onDone(draft.trim() || value);
  return (
    <div className="pin-dialog" role="dialog" aria-modal="true" aria-label="Пароль стола" onClick={done}>
      <form
        className="pin-dialog__box"
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => {
          e.preventDefault();
          done();
        }}
      >
        <strong className="pin-dialog__title">Пароль стола</strong>
        <input
          className="pin-dialog__input"
          inputMode="numeric"
          autoComplete="off"
          maxLength={32}
          value={draft}
          autoFocus
          onFocus={(e) => e.currentTarget.select()}
          onChange={(e) => setDraft(e.target.value)}
        />
        <span className="pin-dialog__hint">Его нужно будет ввести тем, кого вы зовёте за стол (или отправьте им ссылку — она пускает без пароля).</span>
        <button type="submit" className="pin-dialog__ok" disabled={!draft.trim()}>
          Готово
        </button>
      </form>
    </div>
  );
}
