import { VIP_PERKS, type StarPack, type VipPlan } from '@arena/shared';
import { Avatar, Badge } from '@arena/ui';
import { ringOf } from '../lib/cosmetics.js';
import { useStarsPurchase } from '../lib/stars.js';
import { useQuery } from '../lib/useQuery.js';
import { isVip } from '../lib/vip.js';
import { useMe } from '../session.js';
import { QueryView, ScreenHeader } from './common.js';

const dateText = (iso: string) => new Date(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
const daysLeft = (iso: string) => Math.max(1, Math.ceil((Date.parse(iso) - Date.now()) / 86_400_000));
const perDay = (p: VipPlan) => Math.round((p.stars / p.days) * 10) / 10;

/** «VIP»: what it gives and the plans for Telegram Stars. */
export default function VipScreen() {
  const query = useQuery<{ enabled: boolean; packs: StarPack[]; vip: VipPlan[] }>('/stars/packs');
  const me = useMe();
  const vip = isVip(me.premiumUntil);
  const { buy, busy } = useStarsPurchase((order) => `👑 VIP на ${order.days} дн. — корона уже на вашей аватарке!`);

  return (
    <div className="app-stack vip">
      <ScreenHeader title="VIP" subtitle="Корона и привилегии за звёзды Telegram" />
      <section className={`vip-hero${vip ? ' vip-hero--on' : ''}`}>
        <span className="vip-hero__glow" aria-hidden="true" />
        <Avatar id={me.id} name={me.name} photoUrl={me.photoUrl} size={112} ring={me.equipped.frame ? ringOf(me.equipped.frame) : 'gold'} vip />
        <strong className="vip-hero__name">{me.name}</strong>
        {vip ? (
          <span className="vip-hero__status">
            VIP до {dateText(me.premiumUntil!)} · осталось {daysLeft(me.premiumUntil!)} дн.
          </span>
        ) : (
          <span className="vip-hero__status">Так вас увидят за столом с VIP</span>
        )}
      </section>

      <ul className="vip-perks">
        {VIP_PERKS.map((p) => (
          <li key={p.title}>
            <span className="vip-perks__icon" aria-hidden="true">
              {p.icon}
            </span>
            <span>
              <b>{p.title}</b>
              <small>{p.text}</small>
            </span>
          </li>
        ))}
      </ul>

      <h3 className="app-section">{vip ? 'Продлить VIP' : 'Выберите срок'}</h3>
      <QueryView query={query}>
        {({ enabled, vip: plans }) =>
          !enabled ? (
            <p className="app-muted">Покупка за звёзды временно недоступна.</p>
          ) : (
            <div className="vip-plans">
              {plans.map((p) => (
                <button
                  key={p.key}
                  type="button"
                  className={`vip-plan${p.label ? ' vip-plan--hot' : ''}`}
                  disabled={busy !== null}
                  aria-busy={busy === p.key}
                  onClick={() => void buy(p.key)}
                >
                  {p.label && <Badge tone="gold">{p.label}</Badge>}
                  <strong>{p.days}</strong>
                  <span>дней</span>
                  <span className="vip-plan__price">{busy === p.key ? 'Оплата…' : `⭐ ${p.stars}`}</span>
                  <small>{perDay(p)} ⭐ в день</small>
                </button>
              ))}
            </div>
          )
        }
      </QueryView>
      <p className="app-muted coin-shop__note">
        Срок добавляется к оставшемуся VIP. Подсветка ходов и бонус рейтинга действуют, пока идёт срок; корону видят все игроки. Вопросы об
        оплате — команда /paysupport в боте.
      </p>
    </div>
  );
}
