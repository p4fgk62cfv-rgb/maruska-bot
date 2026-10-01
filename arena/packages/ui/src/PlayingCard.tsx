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

/** Illustrated backs (public/backs/<name>.webp); the rest are CSS-drawn. */
const ART_BACKS = new Set(['tartan', 'celtic', 'emerald', 'amethyst', 'frost', 'mandala', 'crystal', 'ruby', 'moon', 'starburst', 'wolf', 'spider']);

/** Card face from the unified 52-card sprite. Sprite order is 2…A, suits S/H/D/C. */
const SPRITE_RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A'] as const;
const SPRITE_SUITS = ['S', 'H', 'D', 'C'] as const;
const DECK_URL = '/cards/deck.webp';
/** Height / width of every card (faces and backs) — the illustrated deck is a tall one. */
export const CARD_RATIO = 1.6;

/**
 * Downloads and decodes the deck sprite (and the chosen back) once, keeping them in memory so
 * cards never flash blank when they move. Safe to call again — it does the work once per URL.
 */
const warmed = new Map<string, HTMLImageElement>();
export function preloadCardArt(back?: string): void {
  if (typeof Image === 'undefined') return;
  const urls = [DECK_URL];
  if (back && ART_BACKS.has(back)) urls.push(`/backs/${back}.webp`);
  for (const url of urls) {
    if (warmed.has(url)) continue;
    const img = new Image();
    img.src = url;
    void img.decode?.().catch(() => undefined);
    warmed.set(url, img);
  }
}

export const PlayingCard = memo(function PlayingCard({ card, faceDown, selected, playable, trump, width = 64, back = 'classic', onClick }: PlayingCardProps) {
  const style = { width, height: width * CARD_RATIO, fontSize: width * 0.28 };
  if (faceDown || !card) {
    return ART_BACKS.has(back) ? (
      <span className="ui-card ui-card--back ui-card--back-art" style={style} aria-label="Карта рубашкой вверх">
        <img className="ui-card__art" src={`/backs/${back}.webp`} alt="" draggable={false} decoding="sync" />
      </span>
    ) : (
      <span className={`ui-card ui-card--back ui-card--back-${back}`} style={style} aria-label="Карта рубашкой вверх" />
    );
  }
  const suit = suitOf(card);
  const rank = RANK_LABEL_RU[rankOf(card)];
  const red = suit === 'H' || suit === 'D';
  const spriteCol = SPRITE_RANKS.indexOf(rankOf(card));
  const spriteRow = SPRITE_SUITS.indexOf(suit);
  const classes = [
    'ui-card',
    'ui-card--art',
    red ? 'ui-card--red' : 'ui-card--black',
    selected && 'ui-card--selected',
    playable && 'ui-card--playable',
    trump && 'ui-card--trump',
  ]
    .filter(Boolean)
    .join(' ');
  // The drawn rank and suit lie under the sprite: until the deck picture is there (slow
  // network), the card still shows what it is instead of a blank.
  const content = (
    <>
      <span className="ui-card__corner" aria-hidden="true">
        <span>{rank}</span>
        <span>{SUIT_SYMBOL[suit]}</span>
      </span>
      <span className="ui-card__pip" aria-hidden="true">{SUIT_SYMBOL[suit]}</span>
      <span className="ui-card__corner ui-card__corner--bottom" aria-hidden="true">
        <span>{rank}</span>
        <span>{SUIT_SYMBOL[suit]}</span>
      </span>
      <span
        className="ui-card__art-sprite"
        style={{ backgroundPosition: `${(spriteCol / 12) * 100}% ${(spriteRow / 3) * 100}%`, backgroundSize: '1300% 400%' }}
        aria-hidden="true"
      />
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
