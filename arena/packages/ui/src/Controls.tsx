import type { ReactNode } from 'react';

export interface TabsProps<T extends string> {
  value: T;
  onChange: (value: T) => void;
  items: { value: T; label: ReactNode }[];
}

export function Tabs<T extends string>({ value, onChange, items }: TabsProps<T>) {
  return (
    <div className="ui-tabs" role="tablist">
      {items.map((item) => (
        <button
          key={item.value}
          role="tab"
          type="button"
          aria-selected={item.value === value}
          className={`ui-tabs__tab${item.value === value ? ' ui-tabs__tab--on' : ''}`}
          onClick={() => onChange(item.value)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="ui-toggle">
      <span>{label}</span>
      <input type="checkbox" role="switch" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="ui-toggle__track" aria-hidden="true">
        <span className="ui-toggle__thumb" />
      </span>
    </label>
  );
}

export function ProgressBar({ value, max, tone = 'violet' }: { value: number; max: number; tone?: 'violet' | 'gold' | 'cyan' }) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <span className={`ui-progress ui-progress--${tone}`} role="progressbar" aria-valuenow={value} aria-valuemax={max}>
      <span style={{ transform: `scaleX(${pct / 100})` }} />
    </span>
  );
}
