import type { BrainParams, StageWeights } from '@arena/game-engine';
import { Button } from '@arena/ui';
import { useEffect, useState } from 'react';
import { useQuery } from '../lib/useQuery.js';
import { useNav } from '../navigation.js';
import { QueryView, ScreenHeader } from './common.js';

interface ProgressDto {
  running: boolean;
  brainVersion: number;
  startedAt: string;
  games: number;
  today: { day: string; games: number };
  generations: number;
  improvements: number;
  lastImprovementAt: string | null;
  tables: { key: string; title: string; games: number }[];
  exams: { at: string; games: number; winRate: number; version: number }[];
  history: { at: string; version: number; score: number }[];
  params: BrainParams;
  defaults: BrainParams;
}

const num = new Intl.NumberFormat('ru-RU');
const pct = (x: number) => `${Math.round(x * 100)}%`;
const time = (iso: string) => new Date(iso).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
const dayTime = (iso: string) => new Date(iso).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

function ago(iso: string | null): string {
  if (!iso) return 'ещё не было';
  const min = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60_000));
  if (min < 1) return 'только что';
  if (min < 60) return `${min} мин назад`;
  const h = Math.floor(min / 60);
  return h < 24 ? `${h} ч ${min % 60} мин назад` : dayTime(iso);
}

const STAGE_RU = { early: 'в начале партии', late: 'когда колода кончается', end: 'в концовке без колоды' } as const;
/** What a weight going up / down means, in a player's words. */
const MEANING: Record<keyof StageWeights, [string, string]> = {
  card: ['дороже ценит старшие некозырные карты', 'легче расстаётся со старшими картами'],
  trump: ['сильнее бережёт козыри', 'смелее тратит козыри'],
  trumpRank: ['особенно бережёт старшие козыри', 'меньше разницы между старшими и младшими козырями'],
  pair: ['собирает пары одного достоинства', 'меньше держится за пары'],
  size: ['спокойнее держит много карт', 'торопится избавиться от карт'],
  take: ['охотнее берёт карты', 'реже берёт, чаще отбивается'],
  transfer: ['чаще переводит', 'реже переводит'],
  throwIn: ['чаще подкидывает, пока соперник отбивается', 'реже подкидывает'],
  unload: ['активнее подкидывает, когда соперник берёт', 'меньше подкидывает берущему'],
  lead: ['чаще ходит несколькими картами сразу', 'чаще ходит по одной карте'],
  cheat: ['чаще жульничает (в режиме «С шулерами»)', 'реже жульничает'],
};

function lessons(p: BrainParams, d: BrainParams) {
  const out: { text: string; stage: string; delta: number }[] = [];
  for (const stage of ['early', 'late', 'end'] as const) {
    for (const key of Object.keys(MEANING) as (keyof StageWeights)[]) {
      const delta = p[stage][key] - d[stage][key];
      if (Math.abs(delta) < 0.05) continue;
      out.push({ text: MEANING[key][delta > 0 ? 0 : 1]!, stage: STAGE_RU[stage], delta });
    }
  }
  return out.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)).slice(0, 8);
}

/** Temporary owner screen: how the strong bot is getting on. */
export default function BotProgressScreen() {
  const query = useQuery<ProgressDto>('/owner/training');
  const { push } = useNav();
  useEffect(() => {
    const timer = setInterval(query.reload, 10_000);
    return () => clearInterval(timer);
  }, [query.reload]);

  return (
    <div className="app-stack bp">
      <ScreenHeader title="Прогресс бота" subtitle="Временное меню — видно только вам" />
      <QueryView query={query}>
        {(d) => {
          const last = d.exams.at(-1);
          const first = d.exams[0];
          const learned = lessons(d.params, d.defaults);
          return (
            <>
              <section className="bp-hero">
                <span className={`bp-status${d.running ? ' bp-status--on' : ''}`}>{d.running ? '● учится прямо сейчас' : '○ на паузе'}</span>
                <strong className="bp-hero__value">{last ? pct(last.winRate) : '—'}</strong>
                <span className="bp-hero__label">побед над прежним максимальным ботом на последнем экзамене</span>
                {last && first && last !== first && (
                  <span className="bp-hero__delta">
                    первый экзамен — {pct(first.winRate)}, сейчас — {pct(last.winRate)}
                  </span>
                )}
              </section>

              <div className="bp-grid">
                <Stat value={`v${d.brainVersion}`} label="версия мозга" />
                <Stat value={num.format(d.improvements)} label="улучшений" />
                <Stat value={ago(d.lastImprovementAt)} label="последнее улучшение" small />
                <Stat value={num.format(d.today.games)} label="партий сегодня" />
                <Stat value={num.format(d.games)} label="партий всего" />
                <Stat value={num.format(d.generations)} label="проверено версий" />
              </div>

              <section className="bp-card">
                <h3>Экзамены против прежнего бота</h3>
                <p className="bp-note">Каждые полчаса — 40 партий. Выше линии 50% — новый бот сильнее старого. На 40 партиях результат прыгает на ±10%, смотрите на общий тренд.</p>
                <ExamChart exams={d.exams.slice(-24)} />
              </section>

              <section className="bp-card">
                <h3>Чему научился</h3>
                {learned.length === 0 ? (
                  <p className="bp-note">Пока играет как в начале — изменения ещё маленькие.</p>
                ) : (
                  <ul className="bp-lessons">
                    {learned.map((l) => (
                      <li key={`${l.stage}${l.text}`}>
                        <span className="bp-lessons__text">
                          {l.text}
                          <small>{l.stage}</small>
                        </span>
                        <span className="bp-lessons__bar" aria-hidden="true">
                          <i style={{ width: `${Math.min(100, Math.abs(l.delta) * 60)}%` }} />
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section className="bp-card">
                <h3>Тренировочные столы</h3>
                <ul className="bp-tables">
                  {d.tables.map((t, i) => (
                    <li key={t.key}>
                      <span>
                        {i + 1}. {t.title}
                      </span>
                      <b>{num.format(t.games)}</b>
                    </li>
                  ))}
                </ul>
                <Button variant="gold" block icon="eye" onClick={() => push('training')}>
                  Смотреть столы
                </Button>
              </section>

              <section className="bp-card">
                <h3>Последние улучшения</h3>
                {d.history.length === 0 ? (
                  <p className="bp-note">Ещё не было — обучение только началось.</p>
                ) : (
                  <ul className="bp-history">
                    {d.history
                      .slice(-10)
                      .reverse()
                      .map((h) => (
                        <li key={h.version}>
                          <b>v{h.version}</b>
                          <span>{dayTime(h.at)}</span>
                          <small>+{(h.score * 100).toFixed(1)}% к прошлой версии</small>
                        </li>
                      ))}
                  </ul>
                )}
              </section>
            </>
          );
        }}
      </QueryView>
    </div>
  );
}

function Stat({ value, label, small }: { value: string; label: string; small?: boolean }) {
  return (
    <span className="bp-stat">
      <b className={small ? 'bp-stat__small' : ''}>{value}</b>
      <small>{label}</small>
    </span>
  );
}

/** Win rate per exam: columns from the baseline, a 50% reference line, the value on tap. */
function ExamChart({ exams }: { exams: ProgressDto['exams'] }) {
  const [picked, setPicked] = useState<number | null>(null);
  if (!exams.length) return <p className="bp-note">Первый экзамен появится в течение получаса после запуска.</p>;
  const shown = picked !== null ? exams[picked] : exams.at(-1);
  return (
    <div className="bp-chart">
      <div className="bp-chart__plot" role="img" aria-label={`Экзамены: ${exams.map((e) => pct(e.winRate)).join(', ')}`}>
        <span className="bp-chart__ref" style={{ bottom: '50%' }}>
          <small>50%</small>
        </span>
        {exams.map((e, i) => (
          <button
            key={e.at}
            type="button"
            className={`bp-chart__col${i === (picked ?? exams.length - 1) ? ' bp-chart__col--on' : ''}`}
            onClick={() => setPicked(i)}
            title={`${dayTime(e.at)}: ${pct(e.winRate)} побед, v${e.version}`}
          >
            <i style={{ height: `${Math.max(2, e.winRate * 100)}%` }} />
          </button>
        ))}
      </div>
      {shown && (
        <p className="bp-chart__caption">
          {time(shown.at)} · версия v{shown.version} · <b>{pct(shown.winRate)}</b> побед из {shown.games} партий
        </p>
      )}
      <table className="bp-sr">
        <tbody>
          {exams.map((e) => (
            <tr key={e.at}>
              <td>{dayTime(e.at)}</td>
              <td>{pct(e.winRate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
