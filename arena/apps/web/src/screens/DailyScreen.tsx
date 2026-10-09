import { QUESTS_BONUS_KEY, type DailyDto, type QuestDto, type Reward } from '@arena/shared';
import { Balance, Button, ProgressBar } from '@arena/ui';
import { useEffect, useState } from 'react';
import { ApiError, api } from '../lib/api.js';
import { haptic } from '../lib/telegram.js';
import { primeCache, useQuery } from '../lib/useQuery.js';
import { useSession } from '../session.js';
import { useToast } from '../toast.js';
import { QueryView, ScreenHeader } from './common.js';

const FORMAT = new Intl.NumberFormat('ru-RU');

function RewardView({ reward, compact }: { reward: Reward; compact?: boolean }) {
  return (
    <span className="daily-reward">
      {reward.credits > 0 && <Balance kind="credits" value={reward.credits} compact={compact} />}
      {reward.coins > 0 && <Balance kind="coins" value={reward.coins} compact={compact} />}
    </span>
  );
}

function rewardToast(reward: Reward): string {
  const parts = [];
  if (reward.credits) parts.push(`${FORMAT.format(reward.credits)} кредитов`);
  if (reward.coins) parts.push(`${reward.coins} монет`);
  return `+${parts.join(' и ')}`;
}

/** «4 ч 12 мин» until the next Moscow day. */
function useCountdown(at: string | undefined): string {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(timer);
  }, []);
  if (!at) return '';
  const left = Math.max(0, Date.parse(at) - now);
  const h = Math.floor(left / 3600_000);
  const m = Math.floor((left % 3600_000) / 60_000);
  return h > 0 ? `${h} ч ${m} мин` : `${Math.max(1, m)} мин`;
}

/** «Задания»: the login calendar and three quests of the day. */
export default function DailyScreen() {
  const query = useQuery<DailyDto>('/daily');
  const { refreshMe } = useSession();
  const toast = useToast();
  const [fresh, setFresh] = useState<DailyDto | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const data = fresh ?? query.data;
  const countdown = useCountdown(data?.resetsAt);

  const claim = (id: string, path: string, reward: Reward, body?: object) => {
    setBusy(id);
    api<DailyDto>(path, { method: 'POST', body })
      .then((next) => {
        haptic.success();
        toast(rewardToast(reward), 'success');
        primeCache('/daily', next);
        setFresh(next);
        return refreshMe();
      })
      .catch((e: unknown) => {
        toast(e instanceof ApiError ? e.message : 'Ошибка', 'error');
        query.reload();
      })
      .finally(() => setBusy(null));
  };

  return (
    <div className="app-stack daily">
      <ScreenHeader title="Задания" />
      <QueryView query={{ ...query, data }}>
        {(d) => {
          const { calendar } = d;
          const today = d.quests.filter((q) => q.day === d.today);
          return (
            <>
              <section className="daily-hero">
                <span className="daily-hero__icon" aria-hidden="true">🎯</span>
                <strong>Награды каждый день</strong>
                <span>Заходите каждый день и выполняйте задания. Новые задания через {countdown}.</span>
              </section>

              <section className="daily-card">
                <header className="daily-card__head">
                  <h3>Календарь входа</h3>
                  <small>{calendar.claimedToday ? 'Сегодня получено' : `День ${calendar.step} из 7`}</small>
                </header>
                <ol className="daily-week">
                  {calendar.rewards.map((reward, i) => {
                    const n = i + 1;
                    const done = n < calendar.step || (n === calendar.step && calendar.claimedToday);
                    const current = n === calendar.step && !calendar.claimedToday;
                    return (
                      <li key={n} className={`daily-day${done ? ' daily-day--done' : ''}${current ? ' daily-day--today' : ''}${n === 7 ? ' daily-day--chest' : ''}`}>
                        <small>{n === 7 ? 'Сундук' : `День ${n}`}</small>
                        <span className="daily-day__icon" aria-hidden="true">{done ? '✓' : n === 7 ? '🎁' : reward.coins ? '🪙' : '💵'}</span>
                        <RewardView reward={reward} compact />
                      </li>
                    );
                  })}
                </ol>
                {calendar.reset && <p className="daily-note">Вы пропустили день — неделя началась заново.</p>}
                {calendar.claimedToday ? (
                  <p className="daily-note">Следующая награда — завтра. Не пропускайте дни: на седьмой день вас ждёт сундук.</p>
                ) : (
                  <Button
                    variant="gold"
                    block
                    loading={busy === 'login'}
                    onClick={() => claim('login', '/daily/login', calendar.rewards[calendar.step - 1]!)}
                  >
                    Забрать награду дня
                  </Button>
                )}
              </section>

              <section className="daily-card">
                <header className="daily-card__head">
                  <h3>Задания дня</h3>
                  <small>{today.filter((q) => q.progress >= q.goal).length} из {today.length}</small>
                </header>
                <ul className="daily-quests">
                  {d.quests.map((q) => (
                    <QuestRow
                      key={`${q.day}:${q.key}`}
                      quest={q}
                      yesterday={q.day !== d.today}
                      busy={busy === `${q.day}:${q.key}`}
                      onClaim={() => claim(`${q.day}:${q.key}`, '/daily/quests', q.reward, { day: q.day, key: q.key })}
                    />
                  ))}
                </ul>
                <div className={`daily-bonus${d.bonus.done && !d.bonus.claimed ? ' daily-bonus--ready' : ''}`}>
                  <span className="daily-bonus__icon" aria-hidden="true">🏅</span>
                  <span className="daily-bonus__text">
                    <strong>Все три задания</strong>
                    <small>Дополнительная награда за весь день</small>
                  </span>
                  {d.bonus.claimed ? (
                    <span className="daily-done">Получено ✓</span>
                  ) : d.bonus.done ? (
                    <Button
                      variant="gold"
                      size="sm"
                      loading={busy === 'bonus'}
                      onClick={() => claim('bonus', '/daily/quests', d.bonus.reward, { day: d.today, key: QUESTS_BONUS_KEY })}
                    >
                      Забрать
                    </Button>
                  ) : (
                    <RewardView reward={d.bonus.reward} />
                  )}
                </div>
              </section>
              <p className="daily-note daily-note--center">Засчитываются все партии — и с людьми, и с ботами.</p>
            </>
          );
        }}
      </QueryView>
    </div>
  );
}

function QuestRow({ quest, yesterday, busy, onClaim }: { quest: QuestDto; yesterday: boolean; busy: boolean; onClaim: () => void }) {
  const done = quest.progress >= quest.goal;
  return (
    <li className={`daily-quest${done && !quest.claimed ? ' daily-quest--ready' : ''}${quest.claimed ? ' daily-quest--claimed' : ''}`}>
      <div className="daily-quest__body">
        <strong>
          {quest.title}
          {yesterday && <em className="daily-quest__tag">вчера</em>}
        </strong>
        <span className="daily-quest__progress">
          <ProgressBar value={quest.progress} max={quest.goal} tone="gold" />
          <small>
            {quest.progress} / {quest.goal}
          </small>
        </span>
      </div>
      <div className="daily-quest__side">
        {quest.claimed ? (
          <span className="daily-done">Получено ✓</span>
        ) : done ? (
          <Button variant="gold" size="sm" loading={busy} onClick={onClaim}>
            Забрать
          </Button>
        ) : (
          <RewardView reward={quest.reward} compact />
        )}
      </div>
    </li>
  );
}
