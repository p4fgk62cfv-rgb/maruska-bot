import { memo } from 'react';
import { RANK_LABEL_RU, SUIT_SYMBOL, rankOf, suitOf, type CardId } from '@arena/game-engine';

export interface PlayingCardProps {
  card?: CardId | null;
  faceDown?: boolean;
  selected?: boolean;
  playable?: boolean;
  trump?: boolean;
  width?: number;
  /** Card back design (item key without the `back_` prefix). */
  back?: string;
  onClick?: () => void;
}

/** Illustrated faces exist for the 36-card deck (6…A); 2–5 of the 52-card deck stay CSS-drawn. */
const ILLUSTRATED = new Set(['6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']);
const FACE_URL = '/cards/';
/** Illustrated backs (public/backs/<name>.webp); the rest are CSS-drawn. */
const ART_BACKS = new Set(['tartan', 'celtic', 'emerald', 'amethyst', 'frost', 'mandala', 'crystal', 'ruby', 'moon', 'starburst', 'wolf', 'spider']);

/** Card face from the illustrated set when there is one, otherwise a CSS card. */
export const PlayingCard = memo(function PlayingCard({ card, faceDown, selected, playable, trump, width = 64, back = 'classic', onClick }: PlayingCardProps) {
  const style = { width, height: width * 1.42, fontSize: width * 0.28 };
  if (faceDown || !card) {
    return ART_BACKS.has(back) ? (
      <span className="ui-card ui-card--back ui-card--back-art" style={style} aria-label="Карта рубашкой вверх">
        <img className="ui-card__art" src={`/backs/${back}.webp`} alt="" draggable={false} decoding="async" />
      </span>
    ) : (
      <span className={`ui-card ui-card--back ui-card--back-${back}`} style={style} aria-label="Карта рубашкой вверх" />
    );
  }
  const suit = suitOf(card);
  const rank = RANK_LABEL_RU[rankOf(card)];
  const red = suit === 'H' || suit === 'D';
  const art = ILLUSTRATED.has(rankOf(card));
  const classes = [
    'ui-card',
    art && 'ui-card--art',
    red ? 'ui-card--red' : 'ui-card--black',
    selected && 'ui-card--selected',
    playable && 'ui-card--playable',
    trump && 'ui-card--trump',
  ]
    .filter(Boolean)
    .join(' ');
  const content = art ? (
    <img className="ui-card__art" src={`${FACE_URL}${card}.webp`} alt="" draggable={false} decoding="async" />
  ) : (
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
