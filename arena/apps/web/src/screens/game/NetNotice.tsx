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
  // Every game update brings a new list: compare who is lost, not the list itself.
  const lostKey = lost.map((p) => `${p.id}\u0000${p.name}`).join('\u0001');

  useEffect(() => {
    const now = new Map(lost.map((p) => [p.id, p.name]));
    const returned = [...before.current].filter(([id]) => !now.has(id)).map(([, name]) => name);
    before.current = now;
    if (now.size > 0) setBack(null);
    else if (returned.length > 0) setBack(returned.join(', '));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lostKey]);

  // «Снова на связи» goes away on its own, whatever the table does meanwhile.
  useEffect(() => {
    if (!back) return;
    const id = window.setTimeout(() => setBack(null), BACK_MS);
    return () => window.clearTimeout(id);
  }, [back]);

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
