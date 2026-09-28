import { type CardId, type PlayerView } from '@arena/game-engine';
import { PlayingCard } from '@arena/ui';
import { useLayoutEffect, useRef } from 'react';
import { motionAllowed } from '../../lib/settings.js';
import { fly } from './motion.js';

export interface TableProps {
  view: PlayerView;
  cardWidth: number;
  /** Table indices the selected card may beat (hints) — highlighted. */
  targets: number[];
  onPair: (index: number) => void;
  onReport: ((seq: number) => void) | null;
  /** «Переводной»: the marked place where a same-rank card passes the attack on. */
  transferSlot: { active: boolean; onDrop: () => void } | null;
  /** The viewer's card back design. */
  back: string;
  /** Where a dragged card would land right now: a pair, the transfer slot or the open felt. */
  hover: string | null;
  /** A card is being dragged — drop zones light up. */
  dragging: boolean;
  /** My move shown before the server confirms it. */
  pending: PendingMove | null;
}

export interface PendingMove {
  cards: CardId[];
  /** Pair index being beaten; null for a lead, a throw-in or a transfer. */
  target: number | null;
  /** Where each card was in the hand, to glide from. */
  from: Record<string, DOMRect>;
  /** State version the move was made on. */
  version: number;
}

const DISCARD_TILT = [-18, 12, -6, 24, -26, 4];

/** Felt with the stock + trump on the left, the discard on the right and up to six pairs in the middle. */
export function Table({ view, cardWidth, targets, onPair, onReport, transferSlot, back, hover, dragging, pending }: TableProps) {
  const trumpCard = view.trump.card;
  const feltRef = useRef<HTMLDivElement>(null);
  /** Where the table cards were after the previous render, and on which state. */
  const placed = useRef<{ version: number; rects: Map<string, DOMRect> }>({ version: -1, rects: new Map() });
  // Pending cards appear where they will lie and glide there from the hand (or the finger).
  // The cards already on the table make room for them smoothly instead of jumping, and
  // slide back if the move is refused. Server updates are animated by the MotionDirector.
  useLayoutEffect(() => {
    if (!motionAllowed() || !feltRef.current) return;
    const moving = new Set<string>(pending?.cards ?? []);
    for (const el of feltRef.current.querySelectorAll<HTMLElement>('[data-card]')) {
      const card = el.dataset.card!;
      const from = moving.has(card) ? pending!.from[card] : placed.current.version === view.version ? placed.current.rects.get(card) : undefined;
      if (from) fly(el, from, el.getBoundingClientRect(), 0);
    }
  }, [pending]);
  useLayoutEffect(() => {
    const rects = new Map<string, DOMRect>();
    for (const el of feltRef.current?.querySelectorAll<HTMLElement>('[data-card]') ?? []) rects.set(el.dataset.card!, el.getBoundingClientRect());
    placed.current = { version: view.version, rects };
  });
  return (
    <div
      ref={feltRef}
      className={`felt${dragging ? ' felt--dragging' : ''}${hover === 'table' ? ' felt--hover' : ''}`}
      data-drop="table"
      style={{ ['--card-w' as string]: `${cardWidth}px` }}
    >
      <div className="felt__deck" data-anchor="deck" aria-label={`В колоде ${view.deckCount}`}>
        {trumpCard ? (
          <>
            <span className="felt__trump" {...(view.deckCount === 1 ? { 'data-anchor': 'deck-card' } : {})}>
              <PlayingCard card={trumpCard} width={cardWidth * 0.9} trump />
            </span>
            {view.deckCount > 1 && (
              <span className="felt__stock" data-anchor="deck-card">
                <PlayingCard faceDown back={back} width={cardWidth * 0.9} />
              </span>
            )}
            <span className="felt__deck-count">{view.deckCount}</span>
          </>
        ) : (
          <span className={`felt__suit felt__suit--${view.trump.suit}`}>{{ S: '♠', H: '♥', D: '♦', C: '♣' }[view.trump.suit]}</span>
        )}
      </div>

      <div className="felt__pairs">
        {view.table.map((pair, index) => (
          <div
            key={pair.attackSeq}
            className={`pair${targets.includes(index) ? ' pair--target' : ''}${pair.defense ? ' pair--beaten' : ''}${hover === `pair:${index}` ? ' pair--hover' : ''}`}
            data-drop={`pair:${index}`}
            onClick={() => onPair(index)}
          >
            <span className="pair__attack" data-card={pair.attack} data-zone="table">
              <PlayingCard card={pair.attack} width={cardWidth} />
              {onReport && pair.by !== view.you?.id && (
                <button type="button" className="pair__report" onClick={(e) => (e.stopPropagation(), onReport(pair.attackSeq))}>
                  !
                </button>
              )}
            </span>
            {!pair.defense && pending?.target === index && (
              <span className="pair__defense pair__defense--pending" data-card={pending.cards[0]} data-zone="table">
                <PlayingCard card={pending.cards[0]!} width={cardWidth} />
              </span>
            )}
            {pair.defense && (
              <span className="pair__defense" data-card={pair.defense} data-zone="table">
                <PlayingCard card={pair.defense as CardId} width={cardWidth} />
                {onReport && pair.defenseBy !== view.you?.id && pair.defenseSeq !== null && (
                  <button type="button" className="pair__report" onClick={(e) => (e.stopPropagation(), onReport(pair.defenseSeq!))}>
                    !
                  </button>
                )}
              </span>
            )}
          </div>
        ))}
        {pending?.target === null &&
          pending.cards.map((card) => (
            <div key={`pending-${card}`} className="pair pair--pending">
              <span className="pair__attack" data-card={card} data-zone="table">
                <PlayingCard card={card} width={cardWidth} />
              </span>
            </div>
          ))}
        {transferSlot && (
          <button
            type="button"
            className={`transfer-slot${transferSlot.active ? ' transfer-slot--active' : ''}${hover === 'transfer' ? ' transfer-slot--hover' : ''}`}
            data-drop="transfer"
            onClick={transferSlot.onDrop}
          >
            <span>⇄</span>
            <span>Перевести</span>
          </button>
        )}
        
      </div>

      <div className="felt__discard" data-anchor="discard" aria-label={`В отбое ${view.discardCount}`}>
        {view.discardCount > 0 && (
          <span className="felt__discard-pile">
            {Array.from({ length: Math.min(6, Math.ceil(view.discardCount / 4)) }, (_, i) => (
              <span key={i} style={{ rotate: `${DISCARD_TILT[i]}deg`, translate: `0 ${i * 14}px` }}>
                <PlayingCard faceDown back={back} width={cardWidth * 0.85} />
              </span>
            ))}
          </span>
        )}
      </div>
    </div>
  );
}
