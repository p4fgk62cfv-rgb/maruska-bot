import type { HTMLAttributes, ReactNode } from 'react';
import { Icon, type IconName } from './Icon.js';

export interface PanelProps extends HTMLAttributes<HTMLDivElement> {
  glow?: 'violet' | 'cyan' | 'gold' | 'none';
  padded?: boolean;
}

/** Glass surface used for every card-like block. */
export function Panel({ glow = 'none', padded = true, className, ...rest }: PanelProps) {
  const classes = ['ui-panel', glow !== 'none' && `ui-panel--glow-${glow}`, padded && 'ui-panel--padded', className]
    .filter(Boolean)
    .join(' ');
  return <div className={classes} {...rest} />;
}

export function Badge({ tone = 'violet', children }: { tone?: 'violet' | 'cyan' | 'gold' | 'green' | 'red' | 'muted'; children: ReactNode }) {
  return <span className={`ui-badge ui-badge--${tone}`}>{children}</span>;
}

export interface ChipProps {
  selected?: boolean;
  onClick?: () => void;
  children: ReactNode;
  disabled?: boolean;
}

export function Chip({ selected, onClick, children, disabled }: ChipProps) {
  return (
    <button type="button" className={`ui-chip${selected ? ' ui-chip--on' : ''}`} aria-pressed={selected} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}

export interface TileProps {
  icon: IconName;
  title: string;
  hint?: string;
  tone?: 'violet' | 'cyan' | 'gold' | 'green' | 'rose';
  onClick?: () => void;
  badge?: ReactNode;
}

export function Tile({ icon, title, hint, tone = 'violet', onClick, badge }: TileProps) {
  return (
    <button type="button" className={`ui-tile ui-tile--${tone}`} onClick={onClick}>
      <span className="ui-tile__icon">
        <Icon name={icon} size={22} />
      </span>
      <span className="ui-tile__text">
        <span className="ui-tile__title">{title}</span>
        {hint && <span className="ui-tile__hint">{hint}</span>}
      </span>
      {badge}
    </button>
  );
}

export function EmptyState({ icon, title, text, action }: { icon: IconName; title: string; text?: string; action?: ReactNode }) {
  return (
    <div className="ui-empty">
      <span className="ui-empty__icon">
        <Icon name={icon} size={30} />
      </span>
      <strong>{title}</strong>
      {text && <p>{text}</p>}
      {action}
    </div>
  );
}

export function Skeleton({ height = 16, width = '100%', radius = 10 }: { height?: number; width?: number | string; radius?: number }) {
  return <span className="ui-skeleton" style={{ height, width, borderRadius: radius }} />;
}
