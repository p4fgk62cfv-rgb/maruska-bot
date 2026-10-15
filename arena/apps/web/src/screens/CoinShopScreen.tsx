import type { StarPack, VipPlan } from '@arena/shared';
import { Badge, Balance, Button, CurrencyIcon, Panel, VipCrown } from '@arena/ui';
import { useStarsPurchase } from '../lib/stars.js';
import { useQuery } from '../lib/useQuery.js';
import { isVip } from '../lib/vip.js';
import { useNav } from '../navigation.js';
import { useMe } from '../session.js';
import { QueryView, ScreenHeader } from './common.js';

/** «Монеты»: packs of coins for Telegram Stars. */
export default function CoinShopScreen() {
  const query = useQuery<{ enabled: boolean; packs: StarPack[]; vip: VipPlan[] }>('/stars/packs');
  const me = useMe();
  const { push } = useNav();
  const { buy, busy } = useStarsPurchase((order) => `+${order.coins} монет — спасибо за покупку!`);

  return (
    <div className="app-stack">
      <ScreenHeader title="Монеты" subtitle="Покупка за звёзды Telegram" />
      <Panel className="coin-shop__balance">
        <span>У вас</span>
        <Balance kind="coins" value={me.wallet.coins} />
        <Button size="sm" variant="ghost" onClick={() => push('items')}>
          Магазин предметов
        </Button>
      </Panel>
      <button type="button" className="vip-banner" onClick={() => push('vip')}>
        <VipCrown className="vip-banner__crown" />
        <span>
          <strong>{isVip(me.premiumUntil) ? 'Вы VIP' : 'Стать VIP'}</strong>
          <small>Золотая корона, подсветка ходов, ×2 рейтинга</small>
        </span>
        <b>{isVip(me.premiumUntil) ? 'Продлить' : 'Подробнее'} ›</b>
      </button>
      <QueryView query={query}>
        {({ enabled, packs }) =>
          !enabled ? (
            <p className="app-muted">Покупка за звёзды временно недоступна.</p>
          ) : (
            <div className="coin-shop">
              {packs.map((p, i) => (
                <Panel key={p.key} className={`coin-pack${p.label ? ' coin-pack--hot' : ''}`}>
                  <span className="coin-pack__icon" aria-hidden="true">
                    {Array.from({ length: Math.min(3, i + 1) }, (_, k) => (
                      <CurrencyIcon key={k} kind="coins" size={30} />
                    ))}
                  </span>
                  <span className="coin-pack__body">
                    <strong>{p.coins.toLocaleString('ru-RU')} монет</strong>
                    <span className="coin-pack__tags">
                      {p.bonus > 0 && <Badge tone="green">+{p.bonus}%</Badge>}
                      {p.label && <Badge tone="gold">{p.label}</Badge>}
                    </span>
                  </span>
                  <Button size="sm" variant="gold" loading={busy === p.key} disabled={busy !== null && busy !== p.key} onClick={() => void buy(p.key)}>
                    ⭐ {p.stars}
                  </Button>
                </Panel>
              ))}
            </div>
          )
        }
      </QueryView>
      <p className="app-muted coin-shop__note">
        Монеты идут на рубашки карт, рамки, смайлы и подсказки в игре. Кредиты для ставок за звёзды не продаются и не выводятся. Вопросы об
        оплате — команда /paysupport в боте.
      </p>
    </div>
  );
}
