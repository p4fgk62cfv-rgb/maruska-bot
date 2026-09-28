import type { FriendDto, RoomDto } from '@arena/shared';
import { Avatar, Balance, BottomSheet, Button, EmptyState, Icon } from '@arena/ui';
import { useQuery } from '../lib/useQuery.js';
import { useState } from 'react';
import { ApiError, api } from '../lib/api.js';
import { useCountdown } from '../lib/hooks.js';
import { haptic, tg } from '../lib/telegram.js';
import { useRealtime } from '../realtime.js';
import { useMe } from '../session.js';
import { useToast } from '../toast.js';
import { DockAction, EmptySeat, SeatTile, TableDock, TableTop } from './game/TableChrome.js';

/** Waiting room: the same felt as the game — chairs fill up live, everyone presses «Готов», the server deals. */
export function RoomScreen({ room }: { room: RoomDto }) {
  const me = useMe();
  const { socket, invite, leaveRoom, status } = useRealtime();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [friendsOpen, setFriendsOpen] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const mySeat = room.seats.find((s) => s.userId === me.id);
  const full = room.seats.length === room.settings.players;
  const left = useCountdown(room.readyDeadline, () => socket.now());
  const others = seatsAfter(room, me.id);

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
  const tileSize = room.settings.players > 4 ? 50 : 58;

  return (
    <div className="game game--room">
      {status !== 'open' && <div className="game__banner">Соединение восстанавливается…</div>}
      <TableTop
        settings={room.settings}
        title={room.tournament ? `${room.tournament.title} · раунд ${room.tournament.round}` : undefined}
        button={{ icon: 'back', label: room.tournament ? 'Сдаться в матче' : 'Выйти', onClick: () => (room.tournament ? setLeaving(true) : void leave()) }}
      />

      <div className={`game__opponents game__opponents--${others.length}`}>
        {others.map(({ number, seat }) =>
          seat ? (
            <SeatTile
              key={seat.userId}
              seat={{ id: seat.userId, name: seat.name, photoUrl: seat.photoUrl, frame: seat.frame, crown: seat.crown }}
              size={tileSize}
              number={number}
              active={seat.ready}
              offline={!seat.connected}
              label={seat.ready ? { text: 'Готов', tone: 'ready' } : null}
            />
          ) : (
            <EmptySeat key={`empty${number}`} number={number} size={tileSize} />
          ),
        )}
      </div>

      <div className="felt">
        <div className="room-center">
          <p className="room-center__hint">{full ? (mySeat?.ready ? 'Ждём остальных…' : 'Нажмите «Готов»') : 'Ждём игроков…'}</p>
          <p className="room-center__sub">
            {full
              ? left !== null
                ? `Кто не нажмёт «Готов» за ${Math.ceil(left / 1000)} с, освободит место`
                : 'Партия начнётся, когда все будут готовы'
              : `Свободно мест: ${room.settings.players - room.seats.length}`}
          </p>
          {room.tournament ? (
            <p className="room-center__sub">Не нажмёте «Готов» вовремя или выйдете — матч засчитается сопернику.</p>
          ) : (
            <>
              {!full && (
                <button type="button" className="room-invite" onClick={() => setFriendsOpen(true)}>
                  Пригласить друзей <Icon name="userPlus" size={26} />
                </button>
              )}
              <div className="room-links">
                <button type="button" onClick={share}>
                  <Icon name="share" size={14} /> Ссылка
                </button>
                <span>
                  Код: <strong>{room.id}</strong>
                </span>
              </div>
            </>
          )}
        </div>
      </div>

      <TableDock
        actions={
          mySeat && (
            <DockAction tone={mySeat.ready ? 'alt' : 'main'} busy={busy} onClick={() => void ready(!mySeat.ready)}>
              {mySeat.ready ? 'Не готов' : 'Готов'}
            </DockAction>
          )
        }
        me={
          <SeatTile
            seat={{ id: me.id, name: me.name, photoUrl: me.photoUrl, frame: me.equipped.frame, crown: me.equipped.crown }}
            size={56}
            active={mySeat?.ready}
            number={mySeat ? mySeat.seat + 1 : undefined}
          />
        }
        extras={
          <span className="room-wallet">
            <Balance kind="credits" value={me.wallet.credits} compact />
            <Balance kind="coins" value={me.wallet.coins} compact />
          </span>
        }
      />

      <BottomSheet open={friendsOpen} title="Позвать друга" onClose={() => setFriendsOpen(false)}>
        {friendsOpen && <FriendPicker seated={room.seats.map((s) => s.userId)} />}
      </BottomSheet>
      <BottomSheet open={leaving} title="Сдаться в матче?" onClose={() => setLeaving(false)}>
        <div className="app-stack">
          <p className="app-muted">Матч засчитается сопернику.</p>
          <Button block variant="danger" onClick={() => (setLeaving(false), void leave())}>Сдаться</Button>
        </div>
      </BottomSheet>
    </div>
  );
}

/** Chairs in play order after mine; empty ones included, numbered from 1. */
function seatsAfter(room: RoomDto, myId: string): { number: number; seat: RoomDto['seats'][number] | null }[] {
  const n = room.settings.players;
  const mine = room.seats.find((s) => s.userId === myId)?.seat ?? -1;
  const out: { number: number; seat: RoomDto['seats'][number] | null }[] = [];
  for (let k = 1; k <= n; k++) {
    const index = (mine + k + n) % n;
    if (index === mine) continue;
    out.push({ number: index + 1, seat: room.seats.find((s) => s.seat === index) ?? null });
  }
  return out;
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
