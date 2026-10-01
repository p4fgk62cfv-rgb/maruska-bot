import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { haptic, setBackButton } from './lib/telegram.js';

export type Tab = 'home' | 'open' | 'private' | 'create';
export type Page =
  | 'filters'
  | 'tournaments'
  | 'friends'
  | 'profile'
  | 'achievements'
  | 'items'
  | 'rules'
  | 'servers'
  | 'leaderboard'
  | 'news'
  | 'settings'
  | 'owner';

interface Navigation {
  tab: Tab;
  stack: Page[];
  setTab: (tab: Tab) => void;
  push: (page: Page) => void;
  back: () => void;
}

const NavContext = createContext<Navigation | null>(null);

/** Tabs plus a page stack; the Telegram BackButton pops the stack. */
export function NavigationProvider({ children }: { children: ReactNode }) {
  const [tab, setTabState] = useState<Tab>('home');
  const [stack, setStack] = useState<Page[]>([]);

  const setTab = useCallback((next: Tab) => {
    haptic.select();
    setStack([]);
    setTabState(next);
  }, []);
  const push = useCallback((page: Page) => {
    haptic.tap();
    setStack((s) => [...s, page]);
  }, []);
  const back = useCallback(() => setStack((s) => s.slice(0, -1)), []);

  useEffect(() => setBackButton(stack.length ? back : null), [stack.length, back]);

  const value = useMemo(() => ({ tab, stack, setTab, push, back }), [tab, stack, setTab, push, back]);
  return <NavContext.Provider value={value}>{children}</NavContext.Provider>;
}

export function useNav(): Navigation {
  const value = useContext(NavContext);
  if (!value) throw new Error('NavigationProvider missing');
  return value;
}
