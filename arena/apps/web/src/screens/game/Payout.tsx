import { CurrencyIcon, formatCompact } from '@arena/ui';
import { useEffect, useRef, useState } from 'react';
import { haptic } from '../../lib/telegram.js';

const SHOW_MS = 1100;
const FLY_MS = 700;

/**
 * Winnings: a big banknote «+17.5K» lands in the middle of the table, then flies down into
 * the balance in the dock. `onDone` fires when it has arrived.
 */
export function Payout({ amount, target, onDone }: { amount: number; target: string; onDone: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const [stage, setStage] = useState<'show' | 'fly'>('show');

  useEffect(() => {
    haptic.success();
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const fly = window.setTimeout(() => setStage('fly'), reduced ? 300 : SHOW_MS);
    const done = window.setTimeout(onDone, reduced ? 400 : SHOW_MS + FLY_MS);
    return () => {
      window.clearTimeout(fly);
      window.clearTimeout(done);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const note = ref.current;
    const to = document.querySelector(target)?.getBoundingClientRect();
    if (stage !== 'fly' || !note || !to) return;
    const from = note.getBoundingClientRect();
    const dx = to.left + to.width / 2 - (from.left + from.width / 2);
    const dy = to.top + to.height / 2 - (from.top + from.height / 2);
    note.animate(
      [
        { translate: '0 0', scale: '1', opacity: 1 },
        { translate: `${dx}px ${dy}px`, scale: '0.25', opacity: 0.4 },
      ],
      { duration: FLY_MS, easing: 'cubic-bezier(0.5, 0, 0.75, 0)', fill: 'forwards' },
    );
  }, [stage, target]);

  return (
    <div className="payout" aria-live="polite">
      <div className="payout__glow" />
      <div className="payout__note" ref={ref}>
        <span className="payout__corner">
          <CurrencyIcon kind="credits" size={24} />
        </span>
        <span className="payout__sum">+{formatCompact(amount)}</span>
        <span className="payout__corner payout__corner--end">
          <CurrencyIcon kind="credits" size={24} />
        </span>
      </div>
    </div>
  );
}
