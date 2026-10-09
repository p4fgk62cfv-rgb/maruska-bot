import type { StarOrderDto, StarPack } from '@arena/shared';
import { Badge, Balance, Button, Panel } from '@arena/ui';
import { useState } from 'react';
import { ApiError, api } from '../lib/api.js';
import { haptic, openInvoice } from '../lib/telegram.js';
import { useQuery } from '../lib/useQuery.js';
import { useNav } from '../navigation.js';
import { useMe, useSession } from '../session.js';
import { useToast } from '../toast.js';
import { QueryView, ScreenHeader } from './common.js';

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Telegram has taken the stars; the bot's confirmation reaches the server a moment later. */
async function waitPaid(id: string, ms: number): Promise<StarOrderDto | null> {
  const until = Date.now() + ms;
  while (Date.now() < until) {
    const order = await api<StarOrderDto>(`/stars/orders/${id}`).catch(() => null);
    if (order?.status === 'PAID') return order;
    await sleep(1500);
  }
  return null;
}

/** «Монеты»: packs of coins for Telegram Stars. */
export default function CoinShopScreen() {
  const query = useQuery<{ enabled: boolean; packs: StarPack[] }>('/stars/packs');
  const me = useMe();
  const { refreshMe } = useSession();
  const { push } = useNav();
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);

  const buy = async (pack: StarPack) => {
    setBusy(pack.key);
    try {
      const { order, link } = await api<{ order: StarOrderDto; link: string }>('/stars/orders', { method: 'POST', body: { pack: pack.key } });
      const status = await openInvoice(link);
      if (status === 'cancelled') return;
      if (status === 'failed') {
        toast('Оплата не прошла', 'error');
        return;
      }
      const paid = await waitPaid(order.id, status === 'paid' ? 30_000 : 120_000);
      if (paid) {
        haptic.success();
        toast(`+${paid.coins} монет — спасибо за покупку!`, 'success');
        await refreshMe();
      } else if (status === 'paid') {
        toast('Оплата получена, монеты появятся в течение нескольких минут', 'info');
      }
    } catch (e) {
      toast(e instanceof ApiError ? e.message : 'Ошибка', 'error');
    } finally {
      setBusy(null);
    }
  };

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
      <QueryView query={query}>
        {({ enabled, packs }) =>
          !enabled ? (
            <p className="app-muted">Покупка за звёзды временно недоступна.</p>
          ) : (
            <div className="coin-shop">
              {packs.map((p, i) => (
                <Panel key={p.key} className={`coin-pack${p.label ? ' coin-pack--hot' : ''}`}>
                  <span className="coin-pack__icon" aria-hidden="true">
                    {'🪙'.repeat(Math.min(3, i + 1))}
                  </span>
                  <span className="coin-pack__body">
                    <strong>{p.coins.toLocaleString('ru-RU')} монет</strong>
                    <span className="coin-pack__tags">
                      {p.bonus > 0 && <Badge tone="green">+{p.bonus}%</Badge>}
                      {p.label && <Badge tone="gold">{p.label}</Badge>}
                    </span>
                  </span>
                  <Button size="sm" variant="gold" loading={busy === p.key} disabled={busy !== null && busy !== p.key} onClick={() => void buy(p)}>
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
