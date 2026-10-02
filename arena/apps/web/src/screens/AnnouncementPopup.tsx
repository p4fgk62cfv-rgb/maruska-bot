import type { AnnouncementDto } from '@arena/shared';
import { Button } from '@arena/ui';
import { useEffect, useState } from 'react';
import { api } from '../lib/api.js';

const SEEN = 'arena.announcement.seen';

/** The owner's message, once per announcement, over the start screen. */
export function AnnouncementPopup() {
  const [shown, setShown] = useState<AnnouncementDto | null>(null);
  useEffect(() => {
    let alive = true;
    api<AnnouncementDto | null>('/announcement')
      .then((a) => {
        let seen: string | null = null;
        try {
          seen = localStorage.getItem(SEEN);
        } catch {
          /* private mode: show it */
        }
        if (alive && a && a.id !== seen) setShown(a);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);
  if (!shown) return null;
  const close = () => {
    try {
      localStorage.setItem(SEEN, shown.id);
    } catch {
      /* ignore */
    }
    setShown(null);
  };
  return (
    <div className="announce" role="dialog" aria-modal="true" aria-label={shown.title || 'Объявление'} onClick={close}>
      <div className="announce__card" onClick={(e) => e.stopPropagation()}>
        <span className="announce__badge">📣</span>
        {shown.title && <h2 className="announce__title">{shown.title}</h2>}
        <p className="announce__text">{shown.text}</p>
        <Button block variant="gold" onClick={close}>Понятно</Button>
      </div>
    </div>
  );
}
