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
/** Suits drawn as shapes: font glyphs differ between phones (and iOS turns them into emoji). */
const SUIT_SHAPE = {
  S: <path d="M50 4C36 24 8 38 8 59c0 16 16 25 31 17 3-2 6-4 8-7-1 11-7 21-17 26h40c-10-5-16-15-17-26 2 3 5 5 8 7 15 8 31-1 31-17C92 38 64 24 50 4z" />,
  H: <path d="M50 93C20 69 5 53 5 33 5 18 16 8 29 8c10 0 17 6 21 14 4-8 11-14 21-14 13 0 24 10 24 25 0 20-15 36-45 60z" />,
  D: <path d="M50 3l37 47-37 47-37-47z" />,
  C: (
    <>
      <circle cx="50" cy="27" r="20" />
      <circle cx="27" cy="57" r="20" />
      <circle cx="73" cy="57" r="20" />
      <circle cx="50" cy="52" r="12" />
      <path d="M46 55c-1 17-6 30-16 40h40c-10-10-15-23-16-40z" />
    </>
  ),
} as const;
const SUIT_RU = { S: 'пики', H: 'червы', D: 'бубны', C: 'трефы' } as const;

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
      <div className="felt__deck" data-anchor="deck" aria-label={`В колоде ${view.deckCount}, козырь ${SUIT_RU[view.trump.suit]}`}>
        {/* Once the deck is gone, the trump suit stays printed on the felt where it lay. */}
        {!trumpCard && (
          <svg className={`felt__suit felt__suit--${view.trump.suit}`} viewBox="0 0 100 100" aria-hidden="true">
            {SUIT_SHAPE[view.trump.suit]}
          </svg>
        )}
        {trumpCard && (
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
