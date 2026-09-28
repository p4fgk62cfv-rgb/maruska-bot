import { type CardId, type PlayerView } from '@arena/game-engine';
import { PlayingCard } from '@arena/ui';

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
}

const DISCARD_TILT = [-18, 12, -6, 24, -26, 4];

/** Felt with the stock + trump on the left, the discard on the right and up to six pairs in the middle. */
export function Table({ view, cardWidth, targets, onPair, onReport, transferSlot, back }: TableProps) {
  const trumpCard = view.trump.card;
  return (
    <div className="felt" style={{ ['--card-w' as string]: `${cardWidth}px` }}>
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
            className={`pair${targets.includes(index) ? ' pair--target' : ''}${pair.defense ? ' pair--beaten' : ''}`}
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
        {transferSlot && (
          <button type="button" className={`transfer-slot${transferSlot.active ? ' transfer-slot--active' : ''}`} onClick={transferSlot.onDrop}>
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
