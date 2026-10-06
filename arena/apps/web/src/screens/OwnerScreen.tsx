import type { AnnouncementDto, BotSettingsDto, OwnerPlayerDto, ReferralSettingsDto, WelcomeGiftDto } from '@arena/shared';
import { Avatar, Balance, Button, Panel, Tabs, Toggle } from '@arena/ui';
import { useEffect, useState } from 'react';
import { ApiError, api } from '../lib/api.js';
import { useQuery } from '../lib/useQuery.js';
import { useSession } from '../session.js';
import { useToast } from '../toast.js';
import { ScreenHeader } from './common.js';
import { useNav } from '../navigation.js';

type Section = 'announcement' | 'gifts' | 'bonus' | 'bots';
interface GiftItem { key: string; name: string; kind: string; owned: boolean }

const KIND_RU: Record<string, string> = { CARD_BACK: 'Рубашка', FRAME: 'Рамка', CROWN: 'Корона', EFFECT: 'Эффект', EMOJI: 'Смайлы', TABLE: 'Стол', AVATAR: 'Аватар' };
const errText = (e: unknown) => (e instanceof ApiError ? e.message : 'Ошибка');

/** «Управление» — only for the game's owners: the start-screen pop-up and gifts to players. */
export default function OwnerScreen() {
  const [section, setSection] = useState<Section>('announcement');
  return (
    <div className="app-stack owner">
      <ScreenHeader title="Управление" subtitle="Видно только владельцу" />
      <Tabs<Section> value={section} onChange={setSection} items={[{ value: 'announcement', label: 'Объявление' }, { value: 'gifts', label: 'Подарки' }, { value: 'bonus', label: 'Бонусы' }, { value: 'bots', label: 'Боты' }]} />
      {section === 'announcement' ? <AnnouncementEditor /> : section === 'gifts' ? <Gifts /> : section === 'bots' ? <><Bots /><Training /></> : <Bonuses />}
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

  // The gift panel is part of the page, not a pop-up: on iPhone, taps inside a scrolled pop-up
  // stopped reaching the buttons after the list refreshed.
  if (picked) {
    return (
      <div className="app-stack">
        <button type="button" className="owner-back" onClick={() => setPicked(null)}>
          ‹ Все игроки
        </button>
        <div className="owner-player owner-player--picked">
          <Avatar id={picked.id} name={picked.name} photoUrl={picked.photoUrl} size={40} />
          <span className="owner-player__body">
            <strong>Подарок: {picked.name}</strong>
            <span>{picked.username ? `@${picked.username}` : ''}</span>
          </span>
        </div>
        <GiftSheet player={picked} onDone={() => players.reload()} />
      </div>
    );
  }

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

const num = (v: string) => Math.max(0, Math.round(Number(v.replace(/\s/g, '')) || 0));
const fmt = (n: number) => n.toLocaleString('ru-RU');

/** Welcome gift for newcomers (toggle + amounts) and a one-off gift to everyone short of credits. */
function Bonuses() {
  const toast = useToast();
  const { refreshMe } = useSession();
  const current = useQuery<WelcomeGiftDto>('/owner/welcome');
  const [enabled, setEnabled] = useState(true);
  const [credits, setCredits] = useState('');
  const [coins, setCoins] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [below, setBelow] = useState('2000');
  const [gCredits, setGCredits] = useState('1000000');
  const [gCoins, setGCoins] = useState('500');
  useEffect(() => {
    if (current.data) {
      setEnabled(current.data.enabled);
      setCredits(String(current.data.credits));
      setCoins(String(current.data.coins));
    }
  }, [current.data]);

  const save = async (next: WelcomeGiftDto) => {
    setBusy('welcome');
    try {
      await api('/owner/welcome', { method: 'PUT', body: next });
      current.reload();
      toast(next.enabled ? `Новички получат ${fmt(next.credits)} кредитов и ${fmt(next.coins)} монет` : 'Подарок новичкам выключен', 'success');
    } catch (e) {
      toast(errText(e), 'error');
    } finally {
      setBusy(null);
    }
  };
  const grant = async () => {
    const body = { below: num(below), credits: num(gCredits), coins: num(gCoins), requestId: crypto.randomUUID() };
    if (!body.below || (!body.credits && !body.coins)) return toast('Укажите суммы', 'error');
    if (!window.confirm(`Начислить ${fmt(body.credits)} кредитов и ${fmt(body.coins)} монет всем, у кого меньше ${fmt(body.below)} кредитов?`)) return;
    setBusy('grant');
    try {
      const r = await api<{ players: number }>('/owner/grant', { method: 'POST', body });
      toast(`Начислено игрокам: ${fmt(r.players)}`, 'success');
      void refreshMe();
    } catch (e) {
      toast(errText(e), 'error');
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <Panel className="owner-card">
        <h3 className="owner-sub">Подарок новичкам</h3>
        <p className="app-muted">Начисляется один раз, когда человек впервые заходит в игру.</p>
        <Toggle
          label={enabled ? 'Включён' : 'Выключен'}
          checked={enabled}
          onChange={(v) => {
            setEnabled(v);
            void save({ enabled: v, credits: num(credits), coins: num(coins) });
          }}
        />
        <label className="owner-field">
          <span>Кредиты</span>
          <input inputMode="numeric" value={credits} onChange={(e) => setCredits(e.target.value)} />
        </label>
        <label className="owner-field">
          <span>Монеты</span>
          <input inputMode="numeric" value={coins} onChange={(e) => setCoins(e.target.value)} />
        </label>
        <Button block variant="gold" loading={busy === 'welcome'} onClick={() => void save({ enabled, credits: num(credits), coins: num(coins) })}>
          Сохранить
        </Button>
      </Panel>
      <Referrals />
      <Panel className="owner-card">
        <h3 className="owner-sub">Раздать всем, у кого мало</h3>
        <label className="owner-field">
          <span>У кого меньше, кредитов</span>
          <input inputMode="numeric" value={below} onChange={(e) => setBelow(e.target.value)} />
        </label>
        <label className="owner-field">
          <span>Начислить кредитов</span>
          <input inputMode="numeric" value={gCredits} onChange={(e) => setGCredits(e.target.value)} />
        </label>
        <label className="owner-field">
          <span>Начислить монет</span>
          <input inputMode="numeric" value={gCoins} onChange={(e) => setGCoins(e.target.value)} />
        </label>
        <Button block variant="gold" loading={busy === 'grant'} onClick={() => void grant()}>
          Начислить
        </Button>
      </Panel>
    </>
  );
}

/** Referral program: coins for the inviter and the newcomer after the newcomer's first game with people. */
function Referrals() {
  const toast = useToast();
  const current = useQuery<ReferralSettingsDto>('/owner/referrals');
  const [enabled, setEnabled] = useState(true);
  const [invitee, setInvitee] = useState('');
  const [referrer, setReferrer] = useState('');
  const [limit, setLimit] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (current.data) {
      setEnabled(current.data.enabled);
      setInvitee(String(current.data.inviteeCoins));
      setReferrer(String(current.data.referrerCoins));
      setLimit(String(current.data.dailyLimit));
    }
  }, [current.data]);

  const save = async (next: ReferralSettingsDto) => {
    if (next.dailyLimit < 1) return toast('Лимит в день — от 1', 'error');
    setBusy(true);
    try {
      await api('/owner/referrals', { method: 'PUT', body: next });
      current.reload();
      toast(next.enabled ? `Приглашения: ${fmt(next.referrerCoins)} пригласившему, ${fmt(next.inviteeCoins)} новичку` : 'Награды за приглашения выключены', 'success');
    } catch (e) {
      toast(errText(e), 'error');
    } finally {
      setBusy(false);
    }
  };
  const draft = (on = enabled): ReferralSettingsDto => ({ enabled: on, inviteeCoins: num(invitee), referrerCoins: num(referrer), dailyLimit: num(limit) });

  return (
    <Panel className="owner-card">
      <h3 className="owner-sub">Приглашения друзей</h3>
      <p className="app-muted">
        Монеты получают оба, когда приглашённый сыграет первую партию с живыми соперниками (партии с ботами не считаются). Лимит защищает от
        накрутки фейковыми аккаунтами: сверх него новичок награду получает, а пригласивший — нет.
      </p>
      <Toggle
        label={enabled ? 'Включены' : 'Выключены'}
        checked={enabled}
        onChange={(v) => {
          setEnabled(v);
          void save(draft(v));
        }}
      />
      <label className="owner-field">
        <span>Монет пригласившему</span>
        <input inputMode="numeric" value={referrer} onChange={(e) => setReferrer(e.target.value)} />
      </label>
      <label className="owner-field">
        <span>Монет новичку</span>
        <input inputMode="numeric" value={invitee} onChange={(e) => setInvitee(e.target.value)} />
      </label>
      <label className="owner-field">
        <span>Оплачиваемых приглашений в сутки</span>
        <input inputMode="numeric" value={limit} onChange={(e) => setLimit(e.target.value)} />
      </label>
      <Button block variant="gold" loading={busy} onClick={() => void save(draft())}>
        Сохранить
      </Button>
    </Panel>
  );
}

const DELAYS = [5, 10, 15, 30, 60];

/** Bot opponents: they take empty seats at public tables when no person comes. */
function Bots() {
  const toast = useToast();
  const current = useQuery<BotSettingsDto>('/owner/bots');
  const [draft, setDraft] = useState<BotSettingsDto | null>(null);
  useEffect(() => {
    if (current.data) setDraft(current.data);
  }, [current.data]);

  const save = async (next: BotSettingsDto) => {
    setDraft(next);
    try {
      await api('/owner/bots', { method: 'PUT', body: next });
      toast(next.enabled ? 'Настройки ботов сохранены' : 'Боты выключены', 'success');
    } catch (e) {
      toast(errText(e), 'error');
      current.reload();
    }
  };

  if (!draft) return <p className="app-muted">Загрузка…</p>;
  return (
    <Panel className="owner-card">
      <h3 className="owner-sub">Боты-соперники</h3>
      <p className="app-muted">
        Боты садятся за столы «Быстрой игры» и за те, где создатель поставил галочку «Добавить ботов», если за указанное время никто
        новый не пришёл. В рейтинг и сезон такие партии не идут, в турниры боты не садятся. Выключатель здесь убирает ботов отовсюду.
      </p>
      <Toggle label={draft.enabled ? 'Включены' : 'Выключены'} checked={draft.enabled} onChange={(v) => void save({ ...draft, enabled: v })} />
      <h3 className="owner-sub">Через сколько садятся</h3>
      <div className="owner-chips">
        {DELAYS.map((d) => (
          <button key={d} type="button" className={`owner-chip${draft.delaySec === d ? ' owner-chip--on' : ''}`} onClick={() => void save({ ...draft, delaySec: d })}>
            {d} с
          </button>
        ))}
      </div>
      <h3 className="owner-sub">Уровни и кредиты</h3>
      <p className="app-muted">
        <b>Минимальный и средний</b> — тренировочные столы: кредиты не ставятся и не выигрываются, заработать на слабых ботах
        нельзя. <b>Максимальный</b> — игра на кредиты; «Быстрая игра» всегда зовёт максимальных ботов. Уровень за своим столом
        игрок выбирает сам.
      </p>
    </Panel>
  );
}

interface TrainingDto {
  running: boolean;
  version: number;
  brainVersion: number;
  games: number;
  today: { day: string; games: number };
  generations: number;
  improvements: number;
  lastImprovementAt: string | null;
  tables: { key: string; title: string; games: number }[];
  exams: { at: string; games: number; winRate: number; version: number }[];
}

const trainingNum = new Intl.NumberFormat('ru-RU');
const when = (iso: string) => new Date(iso).toLocaleString('ru-RU', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' });

/** Self-play training of the strong bots: the three tables, improvements and exams. */
function Training() {
  const query = useQuery<TrainingDto>('/owner/training');
  const { push } = useNav();
  useEffect(() => {
    const timer = setInterval(query.reload, 15_000);
    return () => clearInterval(timer);
  }, [query.reload]);
  const t = query.data;
  if (!t) return <p className="app-muted">Загрузка…</p>;
  const exams = t.exams.slice(-6).reverse();
  return (
    <Panel className="owner-card training">
      <h3 className="owner-sub">Обучение максимальных ботов</h3>
      <p className="app-muted">
        Боты круглосуточно играют друг с другом за тремя столами. Немного изменённая копия бота играет с текущим чемпионом на одинаковых
        раздачах; если она уверенно сильнее — становится чемпионом, и за столами с людьми максимальные боты сразу начинают играть
        по‑новому. Раз в полчаса — экзамен против прежнего максимального бота.
      </p>
      <div className="training-stats">
        <span><b>{t.running ? 'идёт' : 'на паузе'}</b><small>обучение</small></span>
        <span><b>v{t.brainVersion}</b><small>версия мозга</small></span>
        <span><b>{trainingNum.format(t.today.games)}</b><small>партий сегодня</small></span>
        <span><b>{trainingNum.format(t.games)}</b><small>партий всего</small></span>
        <span><b>{trainingNum.format(t.improvements)}</b><small>улучшений</small></span>
        <span><b>{trainingNum.format(t.generations)}</b><small>проверено версий</small></span>
      </div>
      {t.lastImprovementAt && <p className="app-muted">Последнее улучшение: {when(t.lastImprovementAt)}</p>}
      <Button variant="gold" block icon="eye" onClick={() => push('training')}>
        Смотреть, как боты играют
      </Button>
      <h3 className="owner-sub">Столы</h3>
      <ul className="training-tables">
        {t.tables.map((table, i) => (
          <li key={table.key}>
            <span className="training-tables__n">{i + 1}</span>
            <span className="training-tables__title">{table.title}</span>
            <b>{trainingNum.format(table.games)}</b>
          </li>
        ))}
      </ul>
      <h3 className="owner-sub">Экзамены против прежнего максимального бота</h3>
      {exams.length === 0 ? (
        <p className="app-muted">Первый экзамен — примерно через полчаса после запуска.</p>
      ) : (
        <ul className="training-exams">
          {exams.map((e) => (
            <li key={e.at}>
              <span>{when(e.at)} · v{e.version}</span>
              <b className={e.winRate >= 0.5 ? 'training-exams__good' : ''}>{Math.round(e.winRate * 100)}% побед</b>
              <small>{e.games} партий</small>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
