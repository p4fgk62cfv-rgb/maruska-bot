import { Button, EmptyState, Icon, Skeleton } from '@arena/ui';
import type { ReactNode } from 'react';
import type { Query } from '../lib/useQuery.js';
import { useNav } from '../navigation.js';

export function ScreenFallback({ fullscreen }: { fullscreen?: boolean }) {
  return (
    <div className={fullscreen ? 'app-center' : 'app-stack'} aria-busy="true">
      {fullscreen ? (
        <div className="app-splash">
          <span className="app-splash__logo">М</span>
          <span className="app-splash__name">Маруська Арена</span>
        </div>
      ) : (
        <>
          <Skeleton height={28} width="45%" />
          <Skeleton height={120} radius={22} />
          <Skeleton height={64} radius={16} />
          <Skeleton height={64} radius={16} />
        </>
      )}
    </div>
  );
}

export function ScreenHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  const { stack, back } = useNav();
  return (
    <header className="app-header">
      <span className="app-header__side">
        {stack.length > 0 && (
          <button type="button" className="app-header__back" aria-label="Назад" onClick={back}>
            <Icon name="back" size={20} /> Назад
          </button>
        )}
      </span>
      <div className="app-header__titles">
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      <span className="app-header__side app-header__side--end">{action}</span>
    </header>
  );
}

/** Loading / error / data switch shared by every list screen. */
export function QueryView<T>({ query, children }: { query: Query<T>; children: (data: T) => ReactNode }) {
  if (query.data !== undefined) return <>{children(query.data)}</>;
  if (query.error) {
    return (
      <EmptyState
        icon={query.error.code === 'NO_CONNECTION' ? 'wifiOff' : 'close'}
        title={query.error.code === 'NO_CONNECTION' ? 'Нет соединения' : 'Не удалось загрузить'}
        text={query.error.message}
        action={<Button size="sm" onClick={query.reload}>Повторить</Button>}
      />
    );
  }
  return <ScreenFallback />;
}
