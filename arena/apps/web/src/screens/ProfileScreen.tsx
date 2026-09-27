import type { TransactionDto } from '@arena/shared';
import { ratingBadge, RATING } from '@arena/shared';
import { Avatar, Badge, Balance, Panel, ProgressBar, RatingBadge, formatAmount, formatCompact } from '@arena/ui';
import { useQuery } from '../lib/useQuery.js';
import { useNav } from '../navigation.js';
import { useMe } from '../session.js';
import { QueryView, ScreenHeader } from './common.js';

const TX_LABEL: Record<string, string> = {
  SIGNUP_BONUS: 'Приветственный бонус',
  DAILY_BONUS: 'Ежедневный бонус',
  GAME_STAKE: 'Ставка',
  GAME_PAYOUT: 'Выигрыш',
  GAME_REFUND: 'Возврат ставки',
  PURCHASE: 'Покупка',
  TOURNAMENT_FEE: 'Взнос за турнир',
  TOURNAMENT_PRIZE: 'Приз турнира',
  ACHIEVEMENT_REWARD: 'Награда за достижение',
  EXCHANGE: 'Обмен',
  ADMIN: 'Начисление',
};

export default function ProfileScreen() {
  const me = useMe();
  const { push } = useNav();
  const s = me.stats;
  const history = useQuery<TransactionDto[]>('/wallet/transactions?limit=20');

  const badge = ratingBadge(s.rating);
  const stats = [
    { label: 'Игр', value: formatAmount(s.gamesPlayed) },
    { label: 'Побед', value: formatAmount(s.gamesWon) },
    { label: 'Процент побед', value: `${s.winRate}%` },
    { label: 'Выиграно', value: formatCompact(s.totalWinnings) },
    { label: 'Серия', value: String(s.winStreak) },
    { label: 'Лучшая серия', value: String(s.bestStreak) },
  ];

  return (
    <div className="app-stack">
      <ScreenHeader title="Профиль" />
      <Panel glow="violet" className="profile-card">
        <Avatar id={me.id} name={me.name} photoUrl={me.photoUrl} size={84} ring="gold" />
        <h2>{me.name}</h2>
        {me.username && <span className="app-muted">@{me.username}</span>}
        <RatingBadge rating={s.rating} streak={me.bonus.streak} />
        {me.premiumUntil && new Date(me.premiumUntil) > new Date() && (
          <Badge tone="gold">Премиум до {new Date(me.premiumUntil).toLocaleDateString('ru-RU')}</Badge>
        )}
        <div className="profile-card__wallet">
          <Balance kind="credits" value={me.wallet.credits} />
          <Balance kind="coins" value={me.wallet.coins} />
          <Balance kind="diamonds" value={me.wallet.diamonds} />
        </div>
      </Panel>

      <Panel className="league-card">
        <div className="league-card__row">
          <strong style={{ color: badge.league.color }}>{badge.league.name} лига</strong>
          <span className="app-muted">{'★'.repeat(badge.stars)}{'|'.repeat(badge.bars)}</span>
        </div>
        <ProgressBar value={badge.percent} max={100} tone="gold" />
        <span className="app-muted">
          Уровень {badge.level} из {RATING.levelsPerLeague} · {badge.percent}% до следующего
        </span>
        <div className="league-card__row">
          <span className="app-muted">Бонус постоянного игрока</span>
          <Badge tone={me.bonus.availableAt ? 'muted' : 'gold'}>
            ×{me.bonus.multiplier}
            {me.bonus.availableAt ? ` с ${new Date(me.bonus.availableAt).toLocaleTimeString('ru-RU', { timeStyle: 'short' })}` : ' за следующую победу'}
          </Badge>
        </div>
      </Panel>

      <div className="stat-grid">
        {stats.map((item) => (
          <Panel key={item.label} className="stat-grid__cell">
            <strong>{item.value}</strong>
            <span>{item.label}</span>
          </Panel>
        ))}
      </div>

      <Panel className="app-row app-row--between" role="button" tabIndex={0} onClick={() => push('achievements')}>
        <strong>Достижения</strong>
        <Badge tone="gold">{s.achievementsUnlocked} / {s.achievementsTotal}</Badge>
      </Panel>

      <h3 className="app-section">История баланса</h3>
      <QueryView query={history}>
        {(rows) =>
          rows.length === 0 ? (
            <p className="app-muted">Операций пока нет.</p>
          ) : (
            <Panel padded={false} className="tx-list">
              {rows.map((t) => (
                <div key={t.id} className="tx-list__row">
                  <div>
                    <strong>{TX_LABEL[t.type] ?? t.type}</strong>
                    <span className="app-muted">{new Date(t.createdAt).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })}</span>
                  </div>
                  <span className={t.amount >= 0 ? 'tx-plus' : 'tx-minus'}>
                    {t.amount >= 0 ? '+' : '−'}
                    {formatAmount(Math.abs(t.amount))}
                  </span>
                </div>
              ))}
            </Panel>
          )
        }
      </QueryView>
    </div>
  );
}
