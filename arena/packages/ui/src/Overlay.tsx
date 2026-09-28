import { useEffect, type ReactNode } from 'react';
import { Icon } from './Icon.js';

export interface BottomSheetProps {
  open: boolean;
  title?: string;
  onClose: () => void;
  children: ReactNode;
}

export function BottomSheet({ open, title, onClose, children }: BottomSheetProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="ui-sheet" role="dialog" aria-modal="true" aria-label={title}>
      <button type="button" className="ui-sheet__backdrop" aria-label="Закрыть" onClick={onClose} />
      <div className="ui-sheet__body">
        <span className="ui-sheet__grip" />
        {title && (
          <header className="ui-sheet__header">
            <h3>{title}</h3>
            <button type="button" className="ui-icon-btn" aria-label="Закрыть" onClick={onClose}>
              <Icon name="close" />
            </button>
          </header>
        )}
        {children}
      </div>
    </div>
  );
}

export interface ToastItem {
  id: number;
  tone: 'info' | 'error' | 'success';
  text: string;
}

export function ToastStack({ items }: { items: ToastItem[] }) {
  return (
    <div className="ui-toasts" aria-live="polite">
      {items.map((t) => (
        <div key={t.id} className={`ui-toast ui-toast--${t.tone}`}>
          {t.text}
        </div>
      ))}
    </div>
  );
}
