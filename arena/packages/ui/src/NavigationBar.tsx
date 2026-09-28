import { Icon, type IconName } from './Icon.js';

export interface NavItem<T extends string> {
  key: T;
  label: string;
  icon: IconName;
  badge?: number;
  /** The call-to-action tab (e.g. «Создать игру») gets a round gold icon. */
  accent?: boolean;
}

export function NavigationBar<T extends string>({ items, active, onSelect }: { items: NavItem<T>[]; active: T; onSelect: (key: T) => void }) {
  return (
    <nav className="ui-nav">
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          className={`ui-nav__item${item.key === active ? ' ui-nav__item--on' : ''}${item.accent ? ' ui-nav__item--accent' : ''}`}
          aria-current={item.key === active ? 'page' : undefined}
          onClick={() => onSelect(item.key)}
        >
          <span className="ui-nav__icon">
            <Icon name={item.icon} size={22} />
            {item.badge ? <span className="ui-nav__badge">{item.badge}</span> : null}
          </span>
          <span className="ui-nav__label">{item.label}</span>
        </button>
      ))}
    </nav>
  );
}
