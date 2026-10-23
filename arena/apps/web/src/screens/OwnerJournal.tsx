import { BottomSheet, Panel } from '@arena/ui';
import { useEffect, useState } from 'react';
import { ApiError, api } from '../lib/api.js';
import { useQuery } from '../lib/useQuery.js';

interface Problem { at: string; gameId: string | null; miniId: string | null; text: string }
interface SummaryDto {
  hours: number;
  games: number;
  tournaments: number;
  endings: { reason: string; text: string; count: number }[];
  problems: Record<'offline' | 'waits' | 'refused' | 'lostMessages' | 'noShows' | 'forfeits' | 'replays' | 'cancelled' | 'settlementFailed', number>;
  refusedByCode: { code: string; text: string; count: number }[];
  recent: Problem[];
}
interface GameRow {
  id: string;
  startedAt: string;
  status: string;
  durationMs: number | null;
  moves: number;
  players: { name: string; outcome: string | null; place: number | null }[];
  loser: string | null;
  reason: string | null;
  reasonText: string;
  tournament: { title: string; round: number | null } | null;
  flags: { offline: number; waits: number; refused: number; cancelled: number };
}
interface GameDetail extends Omit<GameRow, 'moves' | 'flags'> {
  rules: { players: number; deck: number; speed: string; variant: string; throwIn: string; fairness: string; ending: string };
  timeline: { sec: number; kind: 'move' | 'event'; who: string; text: string; problem?: boolean }[];
}
interface MiniRow {
  id: string;
  title: string;
  chatId: string;
  status: string;
  createdAt: string;
  finishedAt: string | null;
  players: { name: string; place: number | null; round: number | null; why: string | null }[];
  tables: { gameId: string | null; round: number | null; at: string; loser: string | null; reasonText: string }[];
  problems: { at: string; text: string }[];
}

type View = 'summary' | 'games' | 'tournaments';

const time = (iso: string) => new Date(iso).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
const clock = (iso: string) => new Date(iso).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
const minutes = (ms: number | null) => (ms === null ? '' : ms < 60_000 ? `${Math.round(ms / 1000)} с` : `${Math.floor(ms / 60_000)} мин ${Math.round((ms % 60_000) / 1000)} с`);
const errText = (e: unknown) => (e instanceof ApiError ? e.message : 'Ошибка');

/** Problems in plain words, in the order they matter. */
const PROBLEMS: { key: keyof SummaryDto['problems']; icon: string; text: string; hint: string }[] = [
  { key: 'offline', icon: '📵', text: 'Обрывы связи за столом', hint: 'у игрока пропал интернет посреди партии' },
  { key: 'waits', icon: '⏳', text: 'Ход ждал игрока без связи', hint: 'стол держал ход до минуты, пока игрок вернётся' },
  { key: 'refused', icon: '🚫', text: 'Отклонённые ходы', hint: 'карта не легла: не бьёт, не тот ход и т.п.' },
  { key: 'lostMessages', icon: '✉️', text: 'Сообщения турнира не дошли в группу', hint: 'Telegram не принял сообщение и после повторов' },
  { key: 'noShows', icon: '🪑', text: 'Не пришли за стол турнира', hint: 'техническое поражение' },
  { key: 'forfeits', icon: '🚪', text: 'Ушли из-за стола турнира', hint: 'техническое поражение' },
  { key: 'replays', icon: '♻️', text: 'Переигранные столы турнира', hint: 'партия сорвалась и сыграна заново' },
  { key: 'cancelled', icon: '🛑', text: 'Отменённые партии', hint: 'перезапуск сервера или модератор, ставки вернулись' },
  { key: 'settlementFailed', icon: '💥', text: 'Ошибки расчёта партии', hint: 'база не ответила, расчёт повторялся' },
];

/** «Журнал» in «Управление»: what happened in games and tournaments, and why. */
export function OwnerJournal() {
  const [view, setView] = useState<View>('summary');
  const [game, setGame] = useState<string | null>(null);
  return (
    <>
      <div className="owner-chips">
        {(
          [
            ['summary', 'Сводка'],
            ['games', 'Партии'],
            ['tournaments', 'Турниры'],
          ] as const
        ).map(([key, label]) => (
          <button key={key} type="button" className={`owner-chip${view === key ? ' owner-chip--on' : ''}`} onClick={() => setView(key)}>
            {label}
          </button>
        ))}
      </div>
      {view === 'summary' ? <Summary open={setGame} /> : view === 'games' ? <Games open={setGame} /> : <Tournaments open={setGame} />}
      <GameSheet id={game} onClose={() => setGame(null)} />
    </>
  );
}

function Summary({ open }: { open: (id: string) => void }) {
  const [hours, setHours] = useState(24);
  const query = useQuery<SummaryDto>(`/owner/journal/summary?hours=${hours}`);
  const s = query.data;
  return (
    <Panel className="owner-card">
      <div className="owner-chips">
        {[
          [24, 'Сутки'],
          [168, 'Неделя'],
          [720, 'Месяц'],
        ].map(([h, label]) => (
          <button key={h} type="button" className={`owner-chip${hours === h ? ' owner-chip--on' : ''}`} onClick={() => setHours(h as number)}>
            {label}
          </button>
        ))}
      </div>
      {!s ? (
        <p className="app-muted">{query.error ? query.error.message : 'Загрузка…'}</p>
      ) : (
        <>
          <div className="journal-stats">
            <span><b>{s.games}</b> партий</span>
            <span><b>{s.tournaments}</b> турниров</span>
          </div>
          <h3 className="owner-sub">Чем заканчивались партии</h3>
          {s.endings.length ? (
            s.endings.map((e) => (
              <div key={e.reason} className="owner-item">
                <div className="owner-item__body">{e.text}</div>
                <b>{e.count}</b>
              </div>
            ))
          ) : (
            <p className="app-muted">Партий не было.</p>
          )}
          <h3 className="owner-sub">Проблемы</h3>
          {PROBLEMS.map((p) => (
            <div key={p.key} className={`owner-item${s.problems[p.key] ? ' journal-bad' : ''}`}>
              <div className="owner-item__body">
                {p.icon} {p.text}
                <span>{p.hint}</span>
                {p.key === 'refused' && s.refusedByCode.length > 0 && (
                  <span>{s.refusedByCode.map((c) => `${c.text} — ${c.count}`).join(' · ')}</span>
                )}
              </div>
              <b>{s.problems[p.key]}</b>
            </div>
          ))}
          <h3 className="owner-sub">Последние случаи</h3>
          {s.recent.length ? (
            s.recent.map((r, i) => (
              <button key={i} type="button" className="journal-line" disabled={!r.gameId} onClick={() => r.gameId && open(r.gameId)}>
                <span className="journal-line__time">{time(r.at)}</span>
                <span>{r.text}</span>
              </button>
            ))
          ) : (
            <p className="app-muted">Ничего тревожного 👍</p>
          )}
        </>
      )}
    </Panel>
  );
}

function Games({ open }: { open: (id: string) => void }) {
  const [filter, setFilter] = useState<'all' | 'problems' | 'tournament'>('problems');
  const [rows, setRows] = useState<GameRow[] | null>(null);
  const [more, setMore] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async (before?: string) => {
    try {
      const page = await api<GameRow[]>(`/owner/journal/games?filter=${filter}&limit=30${before ? `&before=${encodeURIComponent(before)}` : ''}`);
      setRows((r) => (before && r ? [...r, ...page] : page));
      setMore(page.length === 30);
      setError(null);
    } catch (e) {
      setError(errText(e));
    }
  };
  useEffect(() => {
    setRows(null);
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  return (
    <Panel className="owner-card">
      <div className="owner-chips">
        {(
          [
            ['problems', 'С проблемами'],
            ['tournament', 'Турнирные'],
            ['all', 'Все'],
          ] as const
        ).map(([key, label]) => (
          <button key={key} type="button" className={`owner-chip${filter === key ? ' owner-chip--on' : ''}`} onClick={() => setFilter(key)}>
            {label}
          </button>
        ))}
      </div>
      {error && <p className="app-muted">{error}</p>}
      {!rows ? (
        <p className="app-muted">Загрузка…</p>
      ) : !rows.length ? (
        <p className="app-muted">Партий нет.</p>
      ) : (
        rows.map((g) => (
          <button key={g.id} type="button" className="journal-game" onClick={() => open(g.id)}>
            <span className="journal-game__top">
              <span>{time(g.startedAt)}</span>
              {g.tournament && <span className="journal-tag">🏆 стол {g.tournament.round}</span>}
              <span className="journal-game__len">{minutes(g.durationMs)}</span>
            </span>
            <span className="journal-game__players">{g.players.map((p) => p.name).join(', ')}</span>
            <span className={`journal-game__result${g.reason === 'timeout' || g.reason === 'surrender' || g.reason === 'cancelled' ? ' journal-bad' : ''}`}>
              {g.loser ? `${g.loser} — ${g.reasonText}` : g.reasonText}
            </span>
            {(g.flags.offline > 0 || g.flags.waits > 0 || g.flags.refused > 0 || g.flags.cancelled > 0) && (
              <span className="journal-game__flags">
                {g.flags.offline > 0 && <span>📵 {g.flags.offline}</span>}
                {g.flags.waits > 0 && <span>⏳ {g.flags.waits}</span>}
                {g.flags.refused > 0 && <span>🚫 {g.flags.refused}</span>}
                {g.flags.cancelled > 0 && <span>🛑 {g.flags.cancelled}</span>}
              </span>
            )}
          </button>
        ))
      )}
      {rows && rows.length > 0 && more && (
        <button type="button" className="owner-chip" onClick={() => void load(rows[rows.length - 1]!.startedAt)}>
          Показать ещё
        </button>
      )}
    </Panel>
  );
}

function Tournaments({ open }: { open: (id: string) => void }) {
  const query = useQuery<MiniRow[]>('/owner/journal/tournaments');
  if (!query.data) return <p className="app-muted">{query.error ? query.error.message : 'Загрузка…'}</p>;
  if (!query.data.length) return <p className="app-muted">Турниров ещё не было.</p>;
  return (
    <>
      {query.data.map((m) => (
        <Panel key={m.id} className="owner-card">
          <h3 className="owner-sub">
            🏆 {m.title} <span className="app-muted">· {time(m.createdAt)} · {m.status === 'FINISHED' ? 'окончен' : m.status === 'RUNNING' ? 'идёт' : 'отменён'}</span>
          </h3>
          {m.players.map((p) => (
            <div key={p.name + p.place} className="owner-item">
              <div className="owner-item__body">
                {p.place ? `${p.place}. ` : ''}
                {p.name}
                {p.why && <span>{p.round ? `стол ${p.round}: ` : ''}{p.why}</span>}
              </div>
            </div>
          ))}
          {m.tables.length > 0 && <h3 className="owner-sub">Столы</h3>}
          {m.tables.map((t, i) => (
            <button key={i} type="button" className="journal-line" disabled={!t.gameId} onClick={() => t.gameId && open(t.gameId)}>
              <span className="journal-line__time">{clock(t.at)}</span>
              <span>
                Стол {t.round}: {t.loser ? `${t.loser} — ${t.reasonText}` : t.reasonText}
              </span>
            </button>
          ))}
          {m.problems.length > 0 && <h3 className="owner-sub">Что пошло не так</h3>}
          {m.problems.map((p, i) => (
            <div key={i} className="journal-line journal-bad">
              <span className="journal-line__time">{clock(p.at)}</span>
              <span>{p.text}</span>
            </div>
          ))}
        </Panel>
      ))}
    </>
  );
}

const RULES_RU: Record<string, string> = {
  podkidnoy: 'подкидной', perevodnoy: 'переводной', fast: 'быстро', normal: 'обычно', slow: 'медленно', all: 'подкидывают все',
  neighbors: 'подкидывают соседи', fair: 'честная', cheaters: 'с шулерами', classic: 'классика', draw: 'ничья', nodraw: 'без ничьей',
};

/** One game: who sat, how it ended, and every move and event with its second. */
function GameSheet({ id, onClose }: { id: string | null; onClose: () => void }) {
  const query = useQuery<GameDetail>(id ? `/owner/journal/games/${id}` : null);
  const g = id ? query.data : undefined;
  return (
    <BottomSheet open={id !== null} title="Партия" onClose={onClose}>
      {!g ? (
        <p className="app-muted">{query.error ? query.error.message : 'Загрузка…'}</p>
      ) : (
        <div className="journal-sheet">
          <p className="app-muted">
            {time(g.startedAt)} · {minutes(g.durationMs)}
            {g.tournament ? ` · 🏆 ${g.tournament.title}, стол ${g.tournament.round}` : ''}
            <br />
            {g.rules.players} игр. · {g.rules.deck} карт · {[g.rules.variant, g.rules.speed, g.rules.throwIn, g.rules.fairness, g.rules.ending].map((r) => RULES_RU[r] ?? r).join(' · ')}
          </p>
          <p>
            <b>{g.loser ? `${g.loser} — ${g.reasonText}` : g.reasonText}</b>
          </p>
          <p className="app-muted">{g.players.map((p) => `${p.place ? `${p.place}. ` : ''}${p.name}`).join(', ')}</p>
          <div className="journal-timeline">
            {g.timeline.map((t, i) => (
              <div key={i} className={`journal-line${t.kind === 'event' ? ' journal-line--event' : ''}${t.problem ? ' journal-bad' : ''}`}>
                <span className="journal-line__time">+{t.sec.toFixed(1)} с</span>
                <span>
                  {t.who && <b>{t.who}: </b>}
                  {t.text}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </BottomSheet>
  );
}
