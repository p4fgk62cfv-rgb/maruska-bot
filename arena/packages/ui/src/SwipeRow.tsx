import { useRef, useState, type ReactNode } from 'react';

const ACTION_WIDTH = 96;

/** Swipe right-to-left to reveal a destructive action (e.g. «Удалить»). */
export function SwipeRow({ children, actionLabel, onAction }: { children: ReactNode; actionLabel: string; onAction: () => void }) {
  const [offset, setOffset] = useState(0);
  const start = useRef<{ x: number; y: number; base: number } | null>(null);
  const horizontal = useRef<boolean | null>(null);

  const end = () => {
    setOffset((o) => (o < -ACTION_WIDTH / 2 ? -ACTION_WIDTH : 0));
    start.current = null;
    horizontal.current = null;
  };

  return (
    <div className="ui-swipe">
      {/* Hidden until the row moves: glass cards are translucent and would show the red button through. */}
      <button
        type="button"
        className="ui-swipe__action"
        style={{ width: ACTION_WIDTH, opacity: offset < 0 ? Math.min(1, -offset / (ACTION_WIDTH / 2)) : 0 }}
        onClick={() => (setOffset(0), onAction())}
        tabIndex={offset ? 0 : -1}
      >
        {actionLabel}
      </button>
      <div
        className="ui-swipe__content"
        style={{ transform: `translateX(${offset}px)`, transition: start.current ? 'none' : undefined }}
        onTouchStart={(e) => {
          const t = e.touches[0]!;
          start.current = { x: t.clientX, y: t.clientY, base: offset };
        }}
        onTouchMove={(e) => {
          const s = start.current;
          const t = e.touches[0]!;
          if (!s) return;
          const dx = t.clientX - s.x;
          const dy = t.clientY - s.y;
          // Decide once per gesture whether this is a swipe or a scroll.
          if (horizontal.current === null && Math.abs(dx) + Math.abs(dy) > 8) horizontal.current = Math.abs(dx) > Math.abs(dy);
          if (horizontal.current) setOffset(Math.max(-ACTION_WIDTH * 1.2, Math.min(0, s.base + dx)));
        }}
        onTouchEnd={end}
        onTouchCancel={end}
      >
        {children}
      </div>
    </div>
  );
}
