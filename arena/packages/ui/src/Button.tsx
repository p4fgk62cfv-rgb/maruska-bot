import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { Icon, type IconName } from './Icon.js';

type Variant = 'primary' | 'gold' | 'ghost' | 'danger';
type Size = 'sm' | 'md' | 'lg';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: IconName;
  block?: boolean;
  loading?: boolean;
  children?: ReactNode;
}

export function Button({ variant = 'primary', size = 'md', icon, block, loading, children, className, disabled, ...rest }: ButtonProps) {
  const classes = ['ui-btn', `ui-btn--${variant}`, `ui-btn--${size}`, block && 'ui-btn--block', className]
    .filter(Boolean)
    .join(' ');
  return (
    <button className={classes} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading ? <span className="ui-spinner" /> : icon && <Icon name={icon} size={size === 'lg' ? 22 : 18} />}
      {children && <span>{children}</span>}
    </button>
  );
}

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: IconName;
  label: string;
  badge?: number;
}

export function IconButton({ icon, label, badge, className, ...rest }: IconButtonProps) {
  return (
    <button className={['ui-icon-btn', className].filter(Boolean).join(' ')} aria-label={label} title={label} {...rest}>
      <Icon name={icon} />
      {badge ? <span className="ui-icon-btn__badge">{badge > 99 ? '99+' : badge}</span> : null}
    </button>
  );
}
