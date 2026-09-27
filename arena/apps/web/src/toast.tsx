import { ToastStack, type ToastItem } from '@arena/ui';
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';
import { haptic } from './lib/telegram.js';

type Show = (text: string, tone?: ToastItem['tone']) => void;
const ToastContext = createContext<Show>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const show = useCallback<Show>((text, tone = 'info') => {
    const id = Date.now() + Math.random();
    if (tone === 'error') haptic.error();
    setItems((list) => [...list.slice(-2), { id, text, tone }]);
    setTimeout(() => setItems((list) => list.filter((t) => t.id !== id)), 3200);
  }, []);
  return (
    <ToastContext.Provider value={show}>
      {children}
      <ToastStack items={items} />
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
