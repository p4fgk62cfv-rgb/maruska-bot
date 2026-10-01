import type { AnnouncementDto, OwnerPlayerDto } from '@arena/shared';
import { Avatar, Balance, BottomSheet, Button, Panel, Tabs } from '@arena/ui';
import { useEffect, useState } from 'react';
import { ApiError, api } from '../lib/api.js';
import { useQuery } from '../lib/useQuery.js';
import { useSession } from '../session.js';
import { useToast } from '../toast.js';
import { ScreenHeader } from './common.js';

type Section = 'announcement' | 'gifts';
interface GiftItem { key: string; name: string; kind: string; owned: boolean }

const KIND_RU: Record<string, string> = { CARD_BACK: 'Рубашка', FRAME: 'Рамка', CROWN: 'Корона', EFFECT: 'Эффект', EMOJI: 'Смайлы', TABLE: 'Стол', AVATAR: 'Аватар' };
const errText = (e: unknown) => (e instanceof ApiError ? e.message : 'Ошибка');

/** «Управление» — only for the game's owners: the start-screen pop-up and gifts to players. */
export default function OwnerScreen() {
  const [section, setSection] = useState<Section>('announcement');
  return (
    <div className="app-stack owner">
      <ScreenHeader title="Управление" subtitle="Видно только владельцу" />
      <Tabs<Section> value={section} onChange={setSection} items={[{ value: 'announcement', label: 'Объявление' }, { value: 'gifts', label: 'Подарки' }]} />
      {section === 'announcement' ? <AnnouncementEditor /> : <Gifts />}
    </div>
  );
}

function AnnouncementEditor() {
  const toast = useToast();
  const current = useQuery<AnnouncementDto | null>('/announcement');
  const [title, setTitle] = useState('');
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (current.data) {
      setTitle(current.data.title);
      setText(current.data.text);
    }
  }, [current.data]);

  const save = async () => {
    setBusy(true);
    try {
      await api('/owner/announcement', { method: 'PUT', body: { title, text } });
      current.reload();
      toast('Объявление опубликовано — его увидят все, кто откроет игру', 'success');
    } catch (e) {
      toast(errText(e), 'error');
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    setBusy(true);
    try {
      await api('/owner/announcement', { method: 'DELETE' });
      setTitle('');
      setText('');
      current.reload();
      toast('Объявление снято', 'success');
    } catch (e) {
      toast(errText(e), 'error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel className="owner-card">
      <p className="app-muted">Окно появится на стартовой странице у каждого, кто войдёт в игру. Каждый увидит его один раз; новое объявление покажется всем снова.</p>
      <label className="owner-field">
        <span>Заголовок</span>
        <input value={title} maxLength={80} placeholder="Например: Турнир в субботу!" onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label className="owner-field">
        <span>Текст</span>
        <textarea value={text} maxLength={1500} rows={6} placeholder="Что хотите сказать игрокам" onChange={(e) => setText(e.target.value)} />
      </label>
      <Button block variant="gold" loading={busy} disabled={!text.trim()} onClick={() => void save()}>
        {current.data ? 'Обновить и показать всем' : 'Опубликовать'}
      </Button>
      {current.data && (
        <Button block variant="ghost" disabled={busy} onClick={() => void remove()}>
          Снять объявление
        </Button>
      )}
    </Panel>
  );
}

function Gifts() {
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [picked, setPicked] = useState<OwnerPlayerDto | null>(null);
  useEffect(() => {
    const t = window.setTimeout(() => setQuery(q.trim()), 350);
    return () => window.clearTimeout(t);
  }, [q]);
  const players = useQuery<OwnerPlayerDto[]>(`/owner/players?q=${encodeURIComponent(query)}`);

  return (
    <>
      <input className="owner-search" value={q} placeholder="Имя, @username или Telegram ID" onChange={(e) => setQ(e.target.value)} />
      <div className="app-list">
        {(players.data ?? []).map((p) => (
          <button key={p.id} type="button" className="owner-player" onClick={() => setPicked(p)}>
            <Avatar id={p.id} name={p.name} photoUrl={p.photoUrl} size={40} />
            <span className="owner-player__body">
              <strong>{p.name}</strong>
              <span>
                {p.username ? `@${p.username} · ` : ''}
                <Balance kind="credits" value={p.credits} compact /> <Balance kind="coins" value={p.coins} compact />
              </span>
            </span>
            <span className="owner-player__go">Подарить ›</span>
          </button>
        ))}
        {players.data && players.data.length === 0 && <p className="app-muted">Никого не нашли</p>}
      </div>
      <BottomSheet open={Boolean(picked)} title={picked ? `Подарок: ${picked.name}` : ''} onClose={() => setPicked(null)}>
        {picked && <GiftSheet player={picked} onDone={() => players.reload()} />}
      </BottomSheet>
    </>
  );
}

function GiftSheet({ player, onDone }: { player: OwnerPlayerDto; onDone: () => void }) {
  const toast = useToast();
  const { refreshMe } = useSession();
  const [currency, setCurrency] = useState<'CREDITS' | 'COINS'>('CREDITS');
  const [amount, setAmount] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const items = useQuery<GiftItem[]>(`/owner/players/${player.id}/items`);

  const sendMoney = async (sign: 1 | -1) => {
    const n = Math.round(Number(amount.replace(/\s/g, '')));
    if (!Number.isFinite(n) || n <= 0) return toast('Введите сумму', 'error');
    setBusy('money');
    try {
      const r = await api<{ balance: number }>(`/owner/players/${player.id}/wallet`, {
        method: 'POST',
        body: { currency, amount: sign * n, requestId: crypto.randomUUID() },
      });
      toast(`${sign > 0 ? 'Выдано' : 'Списано'}. Теперь у игрока ${r.balance.toLocaleString('ru-RU')}`, 'success');
      setAmount('');
      onDone();
      void refreshMe();
    } catch (e) {
      toast(errText(e), 'error');
    } finally {
      setBusy(null);
    }
  };
  const toggleItem = async (item: GiftItem) => {
    setBusy(item.key);
    try {
      await api(`/owner/players/${player.id}/items`, { method: 'POST', body: { key: item.key, take: item.owned } });
      toast(item.owned ? `«${item.name}» забран` : `«${item.name}» подарен`, 'success');
      items.reload();
      void refreshMe();
    } catch (e) {
      toast(errText(e), 'error');
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="app-stack">
      <Tabs<'CREDITS' | 'COINS'> value={currency} onChange={setCurrency} items={[{ value: 'CREDITS', label: 'Кредиты' }, { value: 'COINS', label: 'Монеты' }]} />
      <input className="owner-search" inputMode="numeric" value={amount} placeholder="Сумма" onChange={(e) => setAmount(e.target.value)} />
      <div className="owner-row">
        <Button block variant="gold" loading={busy === 'money'} onClick={() => void sendMoney(1)}>Выдать</Button>
        <Button block variant="ghost" disabled={busy === 'money'} onClick={() => void sendMoney(-1)}>Списать</Button>
      </div>
      <h3 className="owner-sub">Предметы</h3>
      <div className="app-list">
        {(items.data ?? []).map((i) => (
          <div key={i.key} className="owner-item">
            <span className="owner-item__body">
              <strong>{i.name}</strong>
              <span>{KIND_RU[i.kind] ?? i.kind}{i.owned ? ' · уже есть' : ''}</span>
            </span>
            <Button size="sm" variant={i.owned ? 'ghost' : 'primary'} loading={busy === i.key} onClick={() => void toggleItem(i)}>
              {i.owned ? 'Забрать' : 'Подарить'}
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}
