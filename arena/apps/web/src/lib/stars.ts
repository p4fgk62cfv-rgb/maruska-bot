import type { StarOrderDto } from '@arena/shared';
import { useState } from 'react';
import { useSession } from '../session.js';
import { useToast } from '../toast.js';
import { ApiError, api } from './api.js';
import { haptic, openInvoice } from './telegram.js';

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

/**
 * Buying a coin pack or VIP for Telegram Stars: the invoice, Telegram's payment form, then the
 * wait for the server to credit it. `busy` is the key being bought.
 */
export function useStarsPurchase(done: (order: StarOrderDto) => string) {
  const { refreshMe } = useSession();
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);

  const buy = async (key: string) => {
    setBusy(key);
    try {
      const { order, link } = await api<{ order: StarOrderDto; link: string }>('/stars/orders', { method: 'POST', body: { pack: key } });
      const status = await openInvoice(link);
      if (status === 'cancelled') return;
      if (status === 'failed') {
        toast('Оплата не прошла', 'error');
        return;
      }
      const paid = await waitPaid(order.id, status === 'paid' ? 30_000 : 120_000);
      if (paid) {
        haptic.success();
        toast(done(paid), 'success');
        await refreshMe();
      } else if (status === 'paid') {
        toast('Оплата получена, покупка появится в течение нескольких минут', 'info');
      }
    } catch (e) {
      toast(e instanceof ApiError ? e.message : 'Ошибка', 'error');
    } finally {
      setBusy(null);
    }
  };

  return { buy, busy };
}
