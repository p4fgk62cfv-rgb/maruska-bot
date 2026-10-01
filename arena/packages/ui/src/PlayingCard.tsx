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

/**
 * Downloads and decodes every illustrated face (and the chosen back) once, keeping them in memory
 * so cards never flash blank when they move. Safe to call again — it does the work once per URL.
 */
const warmed = new Map<string, HTMLImageElement>();
export function preloadCardArt(back?: string): void {
  if (typeof Image === 'undefined') return;
  const urls: string[] = [];
  for (const suit of ['S', 'H', 'D', 'C']) for (const rank of ILLUSTRATED) urls.push(`${FACE_URL}${rank}${suit}.webp`);
  if (back && ART_BACKS.has(back)) urls.push(`/backs/${back}.webp`);
  for (const url of urls) {
    if (warmed.has(url)) continue;
    const img = new Image();
    img.src = url;
    void img.decode?.().catch(() => undefined);
    warmed.set(url, img);
  }
}

/** Card face from the illustrated set when there is one, otherwise a CSS card. */
export const PlayingCard = memo(function PlayingCard({ card, faceDown, selected, playable, trump, width = 64, back = 'classic', onClick }: PlayingCardProps) {
  const style = { width, height: width * 1.42, fontSize: width * 0.28 };
  if (faceDown || !card) {
    return ART_BACKS.has(back) ? (
      <span className="ui-card ui-card--back ui-card--back-art" style={style} aria-label="Карта рубашкой вверх">
        <img className="ui-card__art" src={`/backs/${back}.webp`} alt="" draggable={false} />
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
  // The drawn face lies under the picture: until the picture is there (slow network), the card
  // still shows its rank and suit instead of a blank.
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
      {art && <img className="ui-card__art" src={`${FACE_URL}${card}.webp`} alt="" draggable={false} />}
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
