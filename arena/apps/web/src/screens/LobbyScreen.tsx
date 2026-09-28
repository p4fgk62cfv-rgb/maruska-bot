import { EMPTY_FILTER, formatStake, MODE_PAIRS, type MyRoomDto, type RoomDto, type RoomFilter } from '@arena/shared';
import { BottomSheet, Button, EmptyState, Icon } from '@arena/ui';
import { useEffect, useMemo, useState } from 'react';
import { ApiError, api } from '../lib/api.js';
import { useLobbyFilter } from '../lib/lobbyFilter.js';
import { useNav } from '../navigation.js';
import { useRealtime } from '../realtime.js';
import { useToast } from '../toast.js';
import { ScreenFallback, ScreenHeader } from './common.js';
import { MODE_ICON, RoomRow } from './lobbyParts.js';

const PRIVATE_FILTER: RoomFilter = { ...EMPTY_FILTER, scope: 'private' };

/** «Открытые» and «Приватные»: a live list of tables waiting for players. */
export default function LobbyScreen({ scope }: { scope: 'open' | 'private' }) {
  const { socket, enterRoom } = useRealtime();
  const { setTab } = useNav();
  const toast = useToast();
  const [openFilter] = useLobbyFilter();
  const filter = scope === 'open' ? openFilter : PRIVATE_FILTER;
  const [rooms, setRooms] = useState<RoomDto[] | null>(null);
  const [joining, setJoining] = useState<string | null>(null);
  const [locked, setLocked] = useState<RoomDto | null>(null);
  const [byCode, setByCode] = useState(false);

  // Live lobby: snapshot on (re)subscribe, then created/updated/removed rooms as they happen.
  useEffect(() => {
    setRooms(null);
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
        (a, b) =>
          Number(b.premium) - Number(a.premium) ||
          b.seats.length / b.settings.players - a.seats.length / a.settings.players ||
          b.createdAt - a.createdAt,
      ),
    [rooms],
  );

  const join = (room: RoomDto, password?: string) => {
    setJoining(room.id);
    api<MyRoomDto>(`/rooms/${room.id}/join`, { method: 'POST', body: password ? { password } : {} })
      .then(enterRoom)
      .catch((e: unknown) => toast(e instanceof ApiError ? e.message : 'Ошибка', 'error'))
      .finally(() => setJoining(null));
  };

  const title = scope === 'open' ? 'Открытые игры' : 'Приватные игры';
  return (
    <div className="app-stack lobby">
      <ScreenHeader
        title={title}
        action={
          scope === 'private' ? (
            <button type="button" className="app-bar__action" onClick={() => setByCode(true)}>
              <Icon name="key" size={18} /> Код
            </button>
          ) : undefined
        }
      />
      {scope === 'open' && <FilterBand filter={openFilter} />}

      {!sorted ? (
        <ScreenFallback />
      ) : sorted.length === 0 ? (
        <EmptyState
          icon={scope === 'open' ? 'cards' : 'lock'}
          title={scope === 'open' ? 'Свободных столов нет' : 'Приватных столов нет'}
          text={scope === 'open' ? 'Ослабьте фильтры или создайте свой стол — соперники увидят его сразу.' : 'Создайте стол с паролем и отправьте друзьям приглашение.'}
          action={<Button icon="plus" onClick={() => setTab('create')}>Создать игру</Button>}
        />
      ) : (
        <div className="room-list">
          {sorted.map((room) => (
            <RoomRow key={room.id} room={room} busy={joining === room.id} onOpen={() => (room.isPrivate ? setLocked(room) : join(room))} />
          ))}
        </div>
      )}

      <PasswordSheet room={locked} busy={joining !== null} onClose={() => setLocked(null)} onJoin={(pw) => locked && join(locked, pw)} />
      <CodeSheet open={byCode} onClose={() => setByCode(false)} />
    </div>
  );
}

/** Summary of the current filter; tapping it opens the filter screen. */
function FilterBand({ filter }: { filter: RoomFilter }) {
  const { push } = useNav();
  const stakes =
    filter.stakeMin !== undefined || filter.stakeMax !== undefined
      ? `${formatStake(filter.stakeMin ?? 100)} – ${formatStake(filter.stakeMax ?? 10_000_000)}`
      : 'Любая ставка';
  const players = filter.players.length ? [...filter.players].sort().join(', ') : '2–6';
  return (
    <button type="button" className="filter-band" onClick={() => push('filters')}>
      <span className="filter-band__title">Настройки фильтров</span>
      <span className="filter-band__row">
        <span className="filter-band__modes">
          {MODE_PAIRS.flat().map((m) => (
            <Icon key={m} name={MODE_ICON[m]} size={18} className={filter.modes.includes(m) ? 'is-on' : undefined} />
          ))}
        </span>
        <span className="filter-band__facts">
          <span>{stakes}</span>
          <span>
            {players} <Icon name="user" size={14} />
          </span>
        </span>
        <Icon name="chevron" size={18} />
      </span>
    </button>
  );
}

function PasswordSheet({ room, busy, onClose, onJoin }: { room: RoomDto | null; busy: boolean; onClose: () => void; onJoin: (password: string) => void }) {
  const [password, setPassword] = useState('');
  useEffect(() => setPassword(''), [room]);
  return (
    <BottomSheet open={room !== null} title="Пароль стола" onClose={onClose}>
      <form
        className="app-stack"
        onSubmit={(e) => {
          e.preventDefault();
          onJoin(password);
        }}
      >
        <p className="app-muted">Спросите пароль у создателя стола или попросите ссылку-приглашение — по ней пароль не нужен.</p>
        <input className="app-input" inputMode="numeric" autoFocus maxLength={32} placeholder="Пароль" value={password} onChange={(e) => setPassword(e.target.value)} />
        <Button type="submit" block loading={busy} disabled={!password}>Сесть за стол</Button>
      </form>
    </BottomSheet>
  );
}

function CodeSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { enterRoom } = useRealtime();
  const toast = useToast();
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
    <BottomSheet open={open} title="Вход по коду" onClose={onClose}>
      <div className="app-stack">
        <input className="app-input" placeholder="Код стола, например K7M2QX9A" maxLength={8} value={code} onChange={(e) => setCode(e.target.value)} autoCapitalize="characters" />
        <input className="app-input" placeholder="Пароль" maxLength={32} value={password} onChange={(e) => setPassword(e.target.value)} />
        <Button block loading={busy} disabled={code.trim().length !== 8} onClick={join}>Войти</Button>
      </div>
    </BottomSheet>
  );
}
