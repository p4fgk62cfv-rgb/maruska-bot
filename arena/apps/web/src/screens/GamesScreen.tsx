import { EMPTY_FILTER, formatStake, MODE_LABEL_RU, STAKE_OPTIONS, SPEED_LABEL_RU, type MyRoomDto, type RoomDto, type RoomFilter } from '@arena/shared';
import { BottomSheet, Button, EmptyState, IconButton, Tabs } from '@arena/ui';
import { useEffect, useMemo, useState } from 'react';
import { ApiError, api } from '../lib/api.js';
import { safeStorage } from '../lib/hooks.js';
import { useNav } from '../navigation.js';
import { useRealtime } from '../realtime.js';
import { useToast } from '../toast.js';
import { ScreenFallback, ScreenHeader } from './common.js';
import { ChipGroup, RoomCard } from './lobbyParts.js';

const MODES = ['podkidnoy', 'neighbors', 'cheaters', 'classic', 'perevodnoy', 'all', 'fair', 'draw'] as const;
const FILTER_KEY = 'arena.lobbyFilter';

function toggle<T>(list: readonly T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

function filterCount(f: RoomFilter): number {
  return f.stakes.length + f.players.length + f.deckSizes.length + f.speeds.length + f.modes.length;
}

export default function GamesScreen() {
  const { socket, enterRoom } = useRealtime();
  const { push } = useNav();
  const toast = useToast();
  const [tab, setTab] = useState<'open' | 'private'>('open');
  const [filter, setFilter] = useState<RoomFilter>(() => safeStorage.get(FILTER_KEY, EMPTY_FILTER));
  const [sheet, setSheet] = useState(false);
  const [rooms, setRooms] = useState<RoomDto[] | null>(null);
  const [joining, setJoining] = useState<string | null>(null);

  // Live lobby: snapshot on (re)subscribe, then created/updated/removed rooms as they happen.
  useEffect(() => {
    const offMsg = socket.onMessage((m) => {
      if (m.type === 'LOBBY_SNAPSHOT') setRooms(m.rooms);
      else if (m.type === 'ROOM_CREATED' || m.type === 'ROOM_UPDATED') {
        setRooms((list) => (list ? [m.room, ...list.filter((r) => r.id !== m.room.id)] : list));
      } else if (m.type === 'ROOM_REMOVED') setRooms((list) => (list ? list.filter((r) => r.id !== m.roomId) : list));
    });
    const offOpen = socket.onOpen(() => void socket.send({ type: 'LOBBY_SUBSCRIBE', filter }));
    return () => {
      offMsg();
      offOpen();
      void socket.send({ type: 'LOBBY_UNSUBSCRIBE' });
    };
  }, [socket, filter]);

  const sorted = useMemo(
    () =>
      rooms &&
      [...rooms].sort(
        (a, b) => Number(b.premium) - Number(a.premium) || b.seats.length / b.settings.players - a.seats.length / a.settings.players,
      ),
    [rooms],
  );

  const updateFilter = (next: RoomFilter) => {
    setFilter(next);
    safeStorage.set(FILTER_KEY, next);
  };

  const join = (roomId: string) => {
    setJoining(roomId);
    api<MyRoomDto>(`/rooms/${roomId}/join`, { method: 'POST', body: {} })
      .then(enterRoom)
      .catch((e: unknown) => toast(e instanceof ApiError ? e.message : 'Ошибка', 'error'))
      .finally(() => setJoining(null));
  };

  const count = filterCount(filter);

  return (
    <div className="app-stack">
      <ScreenHeader
        title="Игры"
        action={
          <div className="app-row">
            <IconButton icon="filter" label="Фильтры" badge={count} onClick={() => setSheet(true)} />
            <IconButton icon="plus" label="Создать игру" onClick={() => push('create')} />
          </div>
        }
      />
      <Tabs value={tab} onChange={setTab} items={[{ value: 'open', label: 'Открытые' }, { value: 'private', label: 'Приватные' }]} />

      {tab === 'private' ? (
        <PrivateJoin />
      ) : !sorted ? (
        <ScreenFallback />
      ) : sorted.length === 0 ? (
        <EmptyState
          icon="cards"
          title="Свободных столов нет"
          text={count ? 'Попробуйте ослабить фильтры или создайте свою игру.' : 'Создайте игру — соперники увидят её сразу.'}
          action={<Button icon="plus" onClick={() => push('create')}>Создать игру</Button>}
        />
      ) : (
        <div className="app-list">
          {sorted.map((room) => (
            <RoomCard key={room.id} room={room} busy={joining === room.id} onPlay={() => join(room.id)} />
          ))}
        </div>
      )}

      <BottomSheet open={sheet} title="Фильтры" onClose={() => setSheet(false)}>
        <div className="app-stack">
          <ChipGroup title="Ставка" options={STAKE_OPTIONS} value={filter.stakes} render={formatStake} onToggle={(v) => updateFilter({ ...filter, stakes: toggle(filter.stakes, v) })} />
          <ChipGroup title="Игроки" options={[2, 3, 4, 5, 6] as const} value={filter.players} onToggle={(v) => updateFilter({ ...filter, players: toggle(filter.players, v) })} />
          <ChipGroup title="Колода" options={[24, 36, 52] as const} value={filter.deckSizes} onToggle={(v) => updateFilter({ ...filter, deckSizes: toggle(filter.deckSizes, v) })} />
          <ChipGroup title="Скорость" options={['normal', 'fast'] as const} value={filter.speeds} render={(v) => SPEED_LABEL_RU[v]} onToggle={(v) => updateFilter({ ...filter, speeds: toggle(filter.speeds, v) })} />
          <ChipGroup title="Режим" options={MODES} value={filter.modes} render={(v) => MODE_LABEL_RU[v]} onToggle={(v) => updateFilter({ ...filter, modes: toggle(filter.modes, v) })} />
          <div className="app-row">
            <Button variant="ghost" onClick={() => updateFilter(EMPTY_FILTER)}>Сбросить</Button>
            <Button onClick={() => setSheet(false)}>Показать</Button>
          </div>
        </div>
      </BottomSheet>
    </div>
  );
}

function PrivateJoin() {
  const { enterRoom } = useRealtime();
  const toast = useToast();
  const { push } = useNav();
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);

  const join = () => {
    setBusy(true);
    api<MyRoomDto>(`/rooms/${code.trim().toUpperCase()}/join`, { method: 'POST', body: { password } })
      .then(enterRoom)
      .catch((e: unknown) => toast(e instanceof ApiError ? e.message : 'Ошибка', 'error'))
      .finally(() => setBusy(false));
  };

  return (
    <div className="app-stack">
      <p className="app-muted">Войдите по коду комнаты и паролю или откройте ссылку-приглашение от друга.</p>
      <input className="app-input" placeholder="Код комнаты, например K7M2QX9A" maxLength={8} value={code} onChange={(e) => setCode(e.target.value)} autoCapitalize="characters" />
      <input className="app-input" placeholder="Пароль" type="password" maxLength={32} value={password} onChange={(e) => setPassword(e.target.value)} />
      <Button block loading={busy} disabled={code.trim().length !== 8} onClick={join}>Войти</Button>
      <Button block variant="ghost" icon="lock" onClick={() => push('create')}>Создать приватную игру</Button>
    </div>
  );
}
