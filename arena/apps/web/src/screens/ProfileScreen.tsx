import type { TransactionDto } from '@arena/shared';
import { ratingBadge, RATING } from '@arena/shared';
import { Badge, Balance, Panel, ProgressBar, formatAmount } from '@arena/ui';
import { useQuery } from '../lib/useQuery.js';
import { useNav } from '../navigation.js';
import { useMe } from '../session.js';
import { QueryView, ScreenHeader } from './common.js';
import { PlayerProfileView } from './player/PlayerProfile.js';

const TX_LABEL: Record<string, string> = {
  SIGNUP_BONUS: 'Приветственный бонус',
  DAILY_BONUS: 'Ежедневный бонус',
  GAME_STAKE: 'Ставка',
  GAME_PAYOUT: 'Выигрыш',
  GAME_REFUND: 'Возврат ставки',
  PURCHASE: 'Покупка',
  PURCHASE_REFUND: 'Возврат за предмет',
  TOURNAMENT_FEE: 'Взнос за турнир',
  TOURNAMENT_PRIZE: 'Приз турнира',
  ACHIEVEMENT_REWARD: 'Награда за достижение',
  EXCHANGE: 'Обмен',
  ADMIN: 'Начисление',
};

export default function ProfileScreen() {
  const me = useMe();
  const { push, openPlayer } = useNav();
  const s = me.stats;
  const history = useQuery<TransactionDto[]>('/wallet/transactions?limit=20');
  const badge = ratingBadge(s.rating);

  return (
    <div className="app-stack">
      <ScreenHeader title="Профиль" />
      <PlayerProfileView userId={me.id} onOpenPlayer={openPlayer} onAchievements={() => push('achievements')} />

      <h3 className="app-section">Кошелёк и лига</h3>
      <Panel className="league-card">
        <div className="profile-card__wallet">
          <Balance kind="credits" value={me.wallet.credits} />
          <Balance kind="coins" value={me.wallet.coins} />
          <Balance kind="diamonds" value={me.wallet.diamonds} />
        </div>
        {me.premiumUntil && new Date(me.premiumUntil) > new Date() && (
          <Badge tone="gold">Премиум до {new Date(me.premiumUntil).toLocaleDateString('ru-RU')}</Badge>
        )}
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
