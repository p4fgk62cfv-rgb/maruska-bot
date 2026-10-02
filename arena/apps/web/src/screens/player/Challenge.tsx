import { formatStake, STAKE_OPTIONS, type MyRoomDto, type RoomSettings } from '@arena/shared';
import { BottomSheet, Button, CurrencyIcon } from '@arena/ui';
import { useState } from 'react';
import { ApiError, api } from '../../lib/api.js';
import { safeStorage } from '../../lib/hooks.js';
import { modeText } from '../../lib/people.js';
import { useRealtime } from '../../realtime.js';
import { useMe } from '../../session.js';
import { useToast } from '../../toast.js';
import { Segmented, StakeSlider } from '../lobbyParts.js';

type Draft = Omit<RoomSettings, 'password'>;
/** The same settings the «Создать игру» screen remembers: a friend gets my usual table. */
const DRAFT_KEY = 'arena.createDraft';
const DEFAULT: Draft = {
  stake: 100, players: 2, deckSize: 36, speed: 'normal', variant: 'podkidnoy', throwIn: 'all', fairness: 'fair', ending: 'classic', server: 'almaz', isPrivate: true,
};

/**
 * «Позвать в игру» from the friends list or a player card. At my waiting table: one tap.
 * Otherwise: a private table with my usual rules, the chosen stake and size, and the invite goes out.
 */
export function ChallengeSheet({ friend, onClose }: { friend: { id: string; name: string } | null; onClose: () => void }) {
  const me = useMe();
  const { room, enterRoom } = useRealtime();
  const toast = useToast();
  const [draft, setDraft] = useState<Draft>(() => {
    const saved = { ...DEFAULT, ...safeStorage.get<Partial<Draft>>(DRAFT_KEY, {}) };
    const affordable = STAKE_OPTIONS.filter((s) => s <= Math.max(me.wallet.credits, STAKE_OPTIONS[0]));
    return { ...saved, players: 2, stake: affordable.includes(saved.stake as never) ? saved.stake : affordable[affordable.length - 1]! };
  });
  const [busy, setBusy] = useState(false);
  const atTable = room?.status === 'waiting';
  const full = atTable && room.seats.length >= room.settings.players;

  const invite = async (createFirst: boolean) => {
    if (!friend) return;
    setBusy(true);
    try {
      if (createFirst) {
        // The invite link lets the friend in; the PIN only keeps strangers out.
        const password = String(100_000 + Math.floor(Math.random() * 900_000));
        const mine = await api<MyRoomDto>('/rooms', { method: 'POST', body: { ...draft, isPrivate: true, password } });
        enterRoom(mine);
      }
      await api(`/friends/${friend.id}/invite`, { method: 'POST' });
      toast(`${friend.name} получит приглашение`, 'success');
      onClose();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : 'Ошибка', 'error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <BottomSheet open={friend !== null} title={friend ? `Позвать: ${friend.name}` : ''} onClose={onClose}>
      {friend &&
        (atTable ? (
          <div className="app-stack">
            <p className="app-muted">
              Вы за столом: {modeText({ ...room.settings, players: room.settings.players })}, ставка {formatStake(room.settings.stake)}. Приглашение придёт в
              игру или сообщением от бота.
            </p>
            <Button block size="lg" icon="play" loading={busy} disabled={full} onClick={() => void invite(false)}>
              Позвать за мой стол
            </Button>
            {full && <p className="app-muted">Свободных мест нет.</p>}
          </div>
        ) : (
          <div className="app-stack challenge">
            <div className="challenge__row">
              <span>Ставка</span>
              <strong>
                {formatStake(draft.stake)} <CurrencyIcon kind="credits" size={16} />
              </strong>
            </div>
            <StakeSlider value={draft.stake} max={me.wallet.credits} onChange={(stake) => setDraft({ ...draft, stake })} />
            <div className="challenge__row">
              <span>Игроков</span>
              <Segmented label="Игроков" options={[2, 3, 4, 5, 6] as const} value={draft.players} onToggle={(players) => setDraft({ ...draft, players })} />
            </div>
            <p className="app-muted">{modeText(draft)} · приватный стол. Остальные правила — как в «Создать игру».</p>
            <Button block size="lg" variant="gold" icon="play" loading={busy} disabled={me.wallet.credits < draft.stake} onClick={() => void invite(true)}>
              Создать стол и позвать
            </Button>
          </div>
        ))}
    </BottomSheet>
  );
}
