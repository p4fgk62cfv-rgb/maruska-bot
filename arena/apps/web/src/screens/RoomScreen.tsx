import { formatStake, SPEED_LABEL_RU, type RoomDto } from '@arena/shared';
import type { FriendDto } from '@arena/shared';
import { Avatar, Badge, BottomSheet, Button, EmptyState, Panel, RatingBadge } from '@arena/ui';
import { useQuery } from '../lib/useQuery.js';
import { useState } from 'react';
import { ApiError, api } from '../lib/api.js';
import { useCountdown } from '../lib/hooks.js';
import { haptic, tg } from '../lib/telegram.js';
import { useRealtime } from '../realtime.js';
import { useMe } from '../session.js';
import { useToast } from '../toast.js';
import { modeLabels } from './lobbyParts.js';

/** Waiting room: seats fill up live, everyone presses «Готов», the server deals. */
export function RoomScreen({ room }: { room: RoomDto }) {
  const me = useMe();
  const { socket, invite, leaveRoom, status } = useRealtime();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [friendsOpen, setFriendsOpen] = useState(false);
  const mySeat = room.seats.find((s) => s.userId === me.id);
  const full = room.seats.length === room.settings.players;
  const left = useCountdown(room.readyDeadline, () => socket.now());

  const ready = async (value: boolean) => {
    haptic.tap();
    setBusy(true);
    const reply = await socket.send({ type: 'READY', roomId: room.id, ready: value });
    setBusy(false);
    if (!reply.ok) toast(reply.message, 'error');
  };

  const share = () => {
    if (!invite) return;
    if (tg) tg.openTelegramLink(invite.shareUrl);
    else void navigator.clipboard?.writeText(invite.link).then(() => toast('Ссылка скопирована', 'success'));
  };

  const leave = () => leaveRoom().catch((e: unknown) => toast(e instanceof ApiError ? e.message : 'Ошибка', 'error'));

  return (
    <div className="app-stack room-screen">
      <header className="app-header">
        <div className="app-header__titles">
          <h1>Ставка {formatStake(room.settings.stake)}</h1>
          <p>
            {modeLabels(room.settings).join(' · ')} · {room.settings.deckSize} карт · {SPEED_LABEL_RU[room.settings.speed]}
          </p>
        </div>
        {room.isPrivate && <Badge tone="cyan">Приватная</Badge>}
      </header>

      {status !== 'open' && <Badge tone="red">Соединение восстанавливается…</Badge>}

      <Panel className="room-seats">
        {Array.from({ length: room.settings.players }, (_, i) => {
          const seat = room.seats[i];
          return seat ? (
            <div key={seat.userId} className={`room-seat${seat.ready ? ' room-seat--ready' : ''}`}>
              <Avatar id={seat.userId} name={seat.name} photoUrl={seat.photoUrl} size={52} ring={seat.ready ? 'cyan' : 'none'} status={seat.connected ? 'online' : 'offline'} />
              <strong>{seat.userId === me.id ? 'Вы' : seat.name}</strong>
              <RatingBadge rating={seat.rating} showValue={false} />
              <Badge tone={seat.ready ? 'green' : 'muted'}>{seat.ready ? 'Готов' : 'Ждём'}</Badge>
            </div>
          ) : (
            <div key={`empty${i}`} className="room-seat room-seat--empty">
              <span className="room-seat__empty" />
              <span className="app-muted">Свободно</span>
            </div>
          );
        })}
      </Panel>

      <p className="app-muted room-hint">
        {full
          ? left !== null
            ? `Все места заняты. Нажмите «Готов» — осталось ${Math.ceil(left / 1000)} с`
            : 'Все места заняты. Нажмите «Готов».'
          : `Ждём ещё ${room.settings.players - room.seats.length} игроков`}
      </p>

      {mySeat && (
        <Button size="lg" block variant={mySeat.ready ? 'ghost' : 'gold'} loading={busy} onClick={() => void ready(!mySeat.ready)}>
          {mySeat.ready ? 'Не готов' : 'Готов'}
        </Button>
      )}
      <div className="app-row">
        <Button variant="ghost" icon="users" onClick={() => setFriendsOpen(true)}>Позвать друга</Button>
        <Button variant="ghost" icon="share" onClick={share}>Ссылка</Button>
        <Button variant="danger" onClick={() => void leave()}>Выйти</Button>
      </div>
      <p className="app-muted">Код комнаты: <strong>{room.id}</strong></p>
      <BottomSheet open={friendsOpen} title="Позвать друга" onClose={() => setFriendsOpen(false)}>
        {friendsOpen && <FriendPicker seated={room.seats.map((s) => s.userId)} />}
      </BottomSheet>
    </div>
  );
}

function FriendPicker({ seated }: { seated: string[] }) {
  const query = useQuery<FriendDto[]>('/friends');
  const toast = useToast();
  const [sent, setSent] = useState<string[]>([]);
  const invite = (f: FriendDto) =>
    api(`/friends/${f.id}/invite`, { method: 'POST' })
      .then(() => setSent((s) => [...s, f.id]))
      .catch((e: unknown) => toast(e instanceof ApiError ? e.message : 'Ошибка', 'error'));
  const list = (query.data ?? []).filter((f) => !seated.includes(f.id));
  if (query.data && list.length === 0) {
    return <EmptyState icon="users" title="Некого позвать" text="Добавляйте соперников в друзья — и зовите их одной кнопкой." />;
  }
  return (
    <div className="app-list">
      {list.map((f) => (
        <div key={f.id} className="friend-row">
          <Avatar id={f.id} name={f.name} photoUrl={f.photoUrl} status={f.presence} />
          <div className="friend-row__body">
            <strong>{f.name}</strong>
            <span className="app-muted">{f.presence === 'offline' ? 'придёт сообщение от бота' : f.presence === 'in_game' ? 'сейчас в игре' : 'в сети'}</span>
          </div>
          <Button size="sm" disabled={sent.includes(f.id)} onClick={() => void invite(f)}>
            {sent.includes(f.id) ? 'Позвали' : 'Позвать'}
          </Button>
        </div>
      ))}
    </div>
  );
}
