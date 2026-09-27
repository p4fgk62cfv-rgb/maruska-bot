import type { CardId, Suit } from '@arena/game-engine';
import { PlayingCard } from '@arena/ui';
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
}

/** Overlapping fan that always fits the screen width; selected cards lift up. */
export function Hand({ cards, trump, selected, playable, cardWidth, onTap, onDoubleTap, onSwipeRight }: HandProps) {
  const lastTap = useRef<{ card: CardId; at: number } | null>(null);
  const touch = useRef<number | null>(null);
  const available = Math.min(window.innerWidth, 560) - 32;
  const step = cards.length > 1 ? Math.min(cardWidth * 0.62, (available - cardWidth) / (cards.length - 1)) : 0;

  const tap = (card: CardId) => {
    const now = Date.now();
    if (lastTap.current?.card === card && now - lastTap.current.at < 320) {
      lastTap.current = null;
      onDoubleTap(card);
      return;
    }
    lastTap.current = { card, at: now };
    onTap(card);
  };

  return (
    <div
      className="hand"
      style={{ height: cardWidth * 1.42 + 22, width: step * Math.max(0, cards.length - 1) + cardWidth }}
      onTouchStart={(e) => (touch.current = e.touches[0]?.clientX ?? null)}
      onTouchEnd={(e) => {
        const start = touch.current;
        const end = e.changedTouches[0]?.clientX;
        if (start !== null && end !== undefined && end - start > 60) onSwipeRight();
        touch.current = null;
      }}
    >
      {cards.map((card, i) => (
        <span key={card} className="hand__slot" style={{ transform: `translateX(${i * step}px)`, zIndex: i }}>
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
