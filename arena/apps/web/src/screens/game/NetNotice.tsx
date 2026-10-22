import { useEffect, useRef, useState } from 'react';

const BACK_MS = 2200;

export interface NetNoticeProps {
  /** Players at the table (not me, not bots) whose connection is down right now. */
  lost: { id: string; name: string }[];
  /** The player the turn is waiting for, with the seconds left of the reconnect reserve. */
  waiting: { id: string; seconds: number } | null;
}

/**
 * Over the felt while somebody's connection is in trouble: a spinning wheel and «ждём, пока
 * восстановится связь» (with the seconds left when the turn waits for them), then a short
 * «снова на связи» when they are back.
 */
export function NetNotice({ lost, waiting }: NetNoticeProps) {
  const [back, setBack] = useState<string | null>(null);
  const before = useRef(new Map<string, string>());

  useEffect(() => {
    const now = new Map(lost.map((p) => [p.id, p.name]));
    const returned = [...before.current].filter(([id]) => !now.has(id)).map(([, name]) => name);
    before.current = now;
    if (returned.length === 0 || now.size > 0) return;
    setBack(returned.join(', '));
    const id = window.setTimeout(() => setBack(null), BACK_MS);
    return () => window.clearTimeout(id);
  }, [lost]);

  if (lost.length > 0) {
    const names = lost.map((p) => p.name).join(', ');
    const seconds = waiting && lost.some((p) => p.id === waiting.id) ? waiting.seconds : null;
    return (
      <div className="net-notice" role="status">
        <span className="net-notice__spinner" aria-hidden="true" />
        <span className="net-notice__text">
          <span className="net-notice__title">
            {names}: {lost.length > 1 ? 'проблемы со связью' : 'проблема со связью'}
          </span>
          <span className="net-notice__sub">
            Ждём, пока восстановится связь{seconds !== null ? ` · ещё ${seconds} с` : '…'}
          </span>
        </span>
      </div>
    );
  }
  if (back) {
    return (
      <div className="net-notice net-notice--ok" role="status">
        <span className="net-notice__icon" aria-hidden="true">✓</span>
        <span className="net-notice__title">{back} снова на связи</span>
      </div>
    );
  }
  return null;
}
