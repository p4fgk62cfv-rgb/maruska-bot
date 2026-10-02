import type { FriendDto, RoomDto } from '@arena/shared';
import { Avatar, Balance, BottomSheet, Button, EmptyState, Icon } from '@arena/ui';
import { useQuery } from '../lib/useQuery.js';
import { useEffect, useState } from 'react';
import { ApiError, api } from '../lib/api.js';
import { useCountdown } from '../lib/hooks.js';
import { haptic, tg } from '../lib/telegram.js';
import { useRealtime } from '../realtime.js';
import { useMe } from '../session.js';
import { useToast } from '../toast.js';
import { DockAction, EmptySeat, SeatTile, TableDock, TableTop } from './game/TableChrome.js';
import { EmojiSheet, useSeatEmojis } from './game/emoji.js';

/** Waiting room: the same felt as the game — chairs fill up live, everyone presses «Готов», the server deals. */
export function RoomScreen({ room }: { room: RoomDto }) {
  const me = useMe();
  const { socket, invite, leaveRoom } = useRealtime();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [friendsOpen, setFriendsOpen] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [smiles, setSmiles] = useState(false);
  const emojis = useSeatEmojis(me.id);
  const mySeat = room.seats.find((s) => s.userId === me.id);
  const full = room.seats.length === room.settings.players;
  const left = useCountdown(room.readyDeadline, () => socket.now());
  const others = seatsAfter(room, me.id);
  // Chairs can change only while the table gathers.
  const seating = room.status === 'waiting' && !room.tournament;
  const [askTarget, setAskTarget] = useState<{ userId: string; name: string } | null>(null);
  const [asked, setAsked] = useState<{ userId: string; name: string; seat: number } | null>(null);

  useEffect(
    () =>
      socket.onMessage((m) => {
        if (m.type === 'SEAT_SWAP_ASKED' && m.roomId === room.id) {
          haptic.success();
          setAsked(m.from);
        } else if (m.type === 'SEAT_SWAP_DECLINED' && m.roomId === room.id) {
          toast(`${m.by.name} не хочет меняться местами`, 'info');
        }
      }),
    [socket, room.id, toast],
  );

  const send = async (msg: Parameters<typeof socket.send>[0], ok?: string) => {
    const reply = await socket.send(msg);
    if (!reply.ok) toast(reply.message, 'error');
    else if (ok) toast(ok, 'success');
  };
  const moveTo = (seat: number) => {
    haptic.tap();
    void send({ type: 'MOVE_SEAT', roomId: room.id, seat });
  };

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
  const tileSize = room.settings.players > 5 ? 46 : room.settings.players > 4 ? 50 : 58;

  return (
    <div className="game game--room">
      <TableTop
        settings={room.settings}
        title={room.tournament ? `${room.tournament.title} · раунд ${room.tournament.round}` : undefined}
        button={{ icon: 'back', label: room.tournament ? 'Сдаться в матче' : 'Выйти', onClick: () => (room.tournament ? setLeaving(true) : void leave()) }}
      />

      <div className={`game__opponents game__opponents--${others.length}`}>
        {others.map(({ number, seat }) =>
          seat ? (
            <div key={seat.userId} className="game__opp">
            <button
              type="button"
              className="seat-tap"
              disabled={!seating}
              aria-label={`Поменяться местами с ${seat.name}`}
              onClick={() => setAskTarget({ userId: seat.userId, name: seat.name })}
            >
              <SeatTile
                seat={{ id: seat.userId, name: seat.name, photoUrl: seat.photoUrl, frame: seat.frame, crown: seat.crown }}
                size={tileSize}
                number={number}
                active={seat.ready}
                offline={!seat.connected}
                bot={seat.bot}
                label={seat.ready ? { text: 'Готов', tone: 'ready' } : null}
                emoji={emojis[seat.userId] ?? null}
              />
            </button>
            </div>
          ) : (
            <div key={`empty${number}`} className="game__opp">
              <EmptySeat number={number} size={tileSize} onClick={seating && mySeat ? () => moveTo(number - 1) : undefined} />
            </div>
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
          <button type="button" className="table-dock__avatar" onClick={() => setSmiles((v) => !v)} data-emoji-toggle aria-label="Отправить смайлик" aria-expanded={smiles}>
            <SeatTile
              seat={{ id: me.id, name: me.name, photoUrl: me.photoUrl, frame: me.equipped.frame, crown: me.equipped.crown }}
              size={56}
              active={mySeat?.ready}
              number={mySeat ? mySeat.seat + 1 : undefined}
              emoji={emojis[me.id] ?? null}
            />
          </button>
        }
        extras={
          <span className="room-wallet">
            <Balance kind="credits" value={me.wallet.credits} compact />
            <Balance kind="coins" value={me.wallet.coins} compact />
          </span>
        }
      />

      <EmojiSheet
        open={smiles}
        pack={me.equipped.emoji}
        onClose={() => setSmiles(false)}
        onPick={(emoji) =>
          void socket.send({ type: 'ROOM_EMOJI', roomId: room.id, emoji }).then((reply) => {
            if (!reply.ok) toast(reply.message, 'error');
          })
        }
      />
      <BottomSheet open={askTarget !== null} title="Поменяться местами?" onClose={() => setAskTarget(null)}>
        {askTarget && (
          <div className="app-stack">
            <p className="app-muted">Попросим {askTarget.name} уступить место — вы поменяетесь стульями, если согласится.</p>
            <Button
              block
              variant="gold"
              onClick={() => {
                const target = askTarget;
                setAskTarget(null);
                const bot = room.seats.find((s) => s.userId === target.userId)?.bot;
                void send({ type: 'SEAT_SWAP', roomId: room.id, userId: target.userId }, bot ? undefined : `Просьба отправлена: ${target.name}`);
              }}
            >
              Попросить
            </Button>
          </div>
        )}
      </BottomSheet>
      <BottomSheet open={asked !== null} title="Поменяться местами?" onClose={() => setAsked(null)}>
        {asked && (
          <div className="app-stack">
            <p className="app-muted">
              {asked.name} просит вас уступить место. Вы пересядете на место {asked.seat + 1}.
            </p>
            <Button
              block
              variant="gold"
              onClick={() => {
                const from = asked;
                setAsked(null);
                void send({ type: 'SEAT_SWAP_ANSWER', roomId: room.id, userId: from.userId, accept: true });
              }}
            >
              Уступить место
            </Button>
            <Button
              block
              variant="ghost"
              onClick={() => {
                const from = asked;
                setAsked(null);
                void send({ type: 'SEAT_SWAP_ANSWER', roomId: room.id, userId: from.userId, accept: false });
              }}
            >
              Остаться
            </Button>
          </div>
        )}
      </BottomSheet>
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
