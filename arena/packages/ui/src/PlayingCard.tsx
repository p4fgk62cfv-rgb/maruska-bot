import { memo } from 'react';
import { RANK_LABEL_RU, SUIT_SYMBOL, rankOf, suitOf, type CardId } from '@arena/game-engine';

export interface PlayingCardProps {
  card?: CardId | null;
  faceDown?: boolean;
  selected?: boolean;
  playable?: boolean;
  trump?: boolean;
  width?: number;
  onClick?: () => void;
}

/** Pure CSS/SVG card: no image downloads, crisp on every screen density. */
export const PlayingCard = memo(function PlayingCard({ card, faceDown, selected, playable, trump, width = 64, onClick }: PlayingCardProps) {
  const style = { width, height: width * 1.42, fontSize: width * 0.28 };
  if (faceDown || !card) {
    return <span className="ui-card ui-card--back" style={style} aria-label="Карта рубашкой вверх" />;
  }
  const suit = suitOf(card);
  const rank = RANK_LABEL_RU[rankOf(card)];
  const red = suit === 'H' || suit === 'D';
  const classes = [
    'ui-card',
    red ? 'ui-card--red' : 'ui-card--black',
    selected && 'ui-card--selected',
    playable && 'ui-card--playable',
    trump && 'ui-card--trump',
  ]
    .filter(Boolean)
    .join(' ');
  const content = (
    <>
      <span className="ui-card__corner">
        <span>{rank}</span>
        <span>{SUIT_SYMBOL[suit]}</span>
      </span>
      <span className="ui-card__pip">{SUIT_SYMBOL[suit]}</span>
      <span className="ui-card__corner ui-card__corner--bottom">
        <span>{rank}</span>
        <span>{SUIT_SYMBOL[suit]}</span>
      </span>
    </>
  );
  return onClick ? (
    <button type="button" className={classes} style={style} onClick={onClick} aria-label={`${rank}${SUIT_SYMBOL[suit]}`} aria-pressed={selected}>
      {content}
    </button>
  ) : (
    <span className={classes} style={style} aria-label={`${rank}${SUIT_SYMBOL[suit]}`}>
      {content}
    </span>
  );
});
