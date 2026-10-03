import { useEffect } from 'react';

/**
 * A question in the middle of the table, iPhone-alert style: the text, then «Нет» (bold, the
 * safe answer) and «Да» side by side. Escape or the hardware back answers «Нет».
 */
export function ConfirmAlert({ open, text, onNo, onYes }: { open: boolean; text: string; onNo: () => void; onYes: () => void }) {
  useEffect(() => {
    if (!open) return;
    const key = (e: KeyboardEvent) => e.key === 'Escape' && onNo();
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, [open, onNo]);
  if (!open) return null;
  return (
    <div className="ios-alert-backdrop" role="presentation">
      <div className="ios-alert" role="alertdialog" aria-modal="true" aria-label={text}>
        <p className="ios-alert__text">{text}</p>
        <div className="ios-alert__actions">
          <button type="button" className="ios-alert__btn ios-alert__btn--cancel" onClick={onNo} autoFocus>
            Нет
          </button>
          <button type="button" className="ios-alert__btn" onClick={onYes}>
            Да
          </button>
        </div>
      </div>
    </div>
  );
}

/** The white surrender flag of the table's top-left button. */
export function FlagIcon({ size = 28 }: { size?: number }) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} aria-hidden="true">
      <rect x="5" y="3" width="3" height="27" rx="1.5" fill="#fff" />
      <path d="M8.5 5.2c3.3-1.7 6.3-1 9.1.3 2.7 1.2 5.4 1.9 9 .2v12.6c-3.6 1.7-6.3 1-9-.2-2.8-1.3-5.8-2-9.1-.3z" fill="#fff" />
    </svg>
  );
}
