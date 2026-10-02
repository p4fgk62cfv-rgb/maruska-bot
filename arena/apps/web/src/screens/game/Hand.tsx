import type { CardId, Suit } from '@arena/game-engine';
import { PlayingCard, CARD_RATIO } from '@arena/ui';
import { useRef } from 'react';

export interface HandProps {
  cards: CardId[];
  trump: Suit;
  selected: CardId[];
  playable: Set<CardId> | null;
  cardWidth: number;
  onTap: (card: CardId) => void;
  onDoubleTap: (card: CardId) => void;
  onSwipeRight: () => void;
  /** Finger drag: where the card is now (for hover highlights); null when the drag ends. */
  onDragMove: (card: CardId | null, x: number, y: number) => void;
  /** Resolves true when the drop became a move; otherwise the card flies back into the hand. */
  onDrop: (card: CardId, x: number, y: number) => Promise<boolean> | boolean;
}

/** A gentle fan: outer cards tilt out and sit a little lower. */
function tilt(i: number, n: number): number {
  return n > 1 ? (i - (n - 1) / 2) * Math.min(4, 24 / n) : 0;
}
function arc(i: number, n: number): number {
  const d = n > 1 ? Math.abs(i - (n - 1) / 2) / ((n - 1) / 2) : 0;
  return Math.round(d * d * 10);
}

const DRAG_START = 10;

interface Drag {
  card: CardId;
  el: HTMLElement;
  pointer: number;
  x0: number;
  y0: number;
  base: string;
  active: boolean;
}

/** Overlapping fan that always fits the screen width; selected cards lift up; any card can be dragged onto the table. */
export function Hand({ cards, trump, selected, playable, cardWidth, onTap, onDoubleTap, onSwipeRight, onDragMove, onDrop }: HandProps) {
  const lastTap = useRef<{ card: CardId; at: number } | null>(null);
  const touch = useRef<number | null>(null);
  const drag = useRef<Drag | null>(null);
  const dragged = useRef(false);
  const available = Math.min(window.innerWidth, 560) - 32;
  const step = cards.length > 1 ? Math.min(cardWidth * 0.62, (available - cardWidth) / (cards.length - 1)) : 0;

  const tap = (card: CardId) => {
    if (dragged.current) return;
    const now = Date.now();
    if (lastTap.current?.card === card && now - lastTap.current.at < 320) {
      lastTap.current = null;
      onDoubleTap(card);
      return;
    }
    lastTap.current = { card, at: now };
    onTap(card);
  };

  const settle = (el: HTMLElement, base: string) => {
    el.classList.remove('hand__slot--drag');
    el.classList.add('hand__slot--return');
    el.style.transform = base;
    window.setTimeout(() => el.classList.remove('hand__slot--return'), 260);
  };

  const down = (card: CardId, e: React.PointerEvent<HTMLElement>) => {
    if (e.button !== 0 || drag.current) return;
    drag.current = { card, el: e.currentTarget, pointer: e.pointerId, x0: e.clientX, y0: e.clientY, base: e.currentTarget.style.transform, active: false };
    dragged.current = false;
  };

  const move = (e: React.PointerEvent<HTMLElement>) => {
    const d = drag.current;
    if (!d || d.pointer !== e.pointerId) return;
    const dx = e.clientX - d.x0;
    const dy = e.clientY - d.y0;
    if (!d.active) {
      if (Math.hypot(dx, dy) < DRAG_START) return;
      d.active = true;
      dragged.current = true;
      d.el.setPointerCapture(e.pointerId);
      d.el.classList.add('hand__slot--drag');
    }
    // The card follows the finger upright and a little bigger, above everything else.
    d.el.style.transform = `${d.base.replace(/rotate\([^)]*\)/, '')} translate(${dx}px, ${dy}px) scale(1.1)`;
    onDragMove(d.card, e.clientX, e.clientY);
  };

  const up = async (e: React.PointerEvent<HTMLElement>) => {
    const d = drag.current;
    if (!d || d.pointer !== e.pointerId) return;
    drag.current = null;
    if (!d.active) return;
    onDragMove(null, 0, 0);
    // The click that follows a drag must not select the card.
    window.setTimeout(() => (dragged.current = false), 50);
    const ok = e.type === 'pointerup' && (await onDrop(d.card, e.clientX, e.clientY));
    if (!ok) settle(d.el, d.base);
  };

  return (
    <div
      className="hand"
      style={{ height: cardWidth * CARD_RATIO + 30, width: step * Math.max(0, cards.length - 1) + cardWidth }}
      onTouchStart={(e) => (touch.current = e.touches[0]?.clientX ?? null)}
      onTouchEnd={(e) => {
        const start = touch.current;
        const end = e.changedTouches[0]?.clientX;
        if (!dragged.current && start !== null && end !== undefined && end - start > 60) onSwipeRight();
        touch.current = null;
      }}
    >
      {cards.map((card, i) => (
        <span
          key={card}
          className="hand__slot"
          data-card={card}
          data-zone="hand"
          style={{ transform: `translateX(${i * step}px) translateY(${arc(i, cards.length)}px) rotate(${tilt(i, cards.length)}deg)`, zIndex: i }}
          onPointerDown={(e) => down(card, e)}
          onPointerMove={move}
          onPointerUp={up}
          onPointerCancel={up}
        >
          <PlayingCard
            card={card}
            width={cardWidth}
            selected={selected.includes(card)}
            playable={playable?.has(card) ?? false}
            trump={card.endsWith(trump)}
            onClick={() => tap(card)}
          />
        </span>
      ))}
    </div>
  );
}
