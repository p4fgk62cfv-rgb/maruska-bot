import { Icon } from './Icon.js';

const FORMAT = new Intl.NumberFormat('ru-RU');

export function formatAmount(value: number): string {
  return FORMAT.format(value);
}

/** 1 754 833 → "1.75M" for tight places like seats and lobby cards. */
export function formatCompact(value: number): string {
  if (value >= 1_000_000) return `${+(value / 1_000_000).toFixed(2)}M`;
  if (value >= 10_000) return `${+(value / 1_000).toFixed(1)}K`;
  return FORMAT.format(value);
}

export interface BalanceProps {
  kind: 'credits' | 'coins' | 'diamonds';
  value: number;
  compact?: boolean;
}

const ICON = { credits: 'chip', coins: 'coin', diamonds: 'gem' } as const;
const LABEL = { credits: 'Кредиты', coins: 'Монеты', diamonds: 'Алмазы' } as const;

export function Balance({ kind, value, compact }: BalanceProps) {
  return (
    <span className={`ui-balance ui-balance--${kind}`} title={LABEL[kind]}>
      <Icon name={ICON[kind]} size={16} />
      <span>{compact ? formatCompact(value) : formatAmount(value)}</span>
    </span>
  );
}
