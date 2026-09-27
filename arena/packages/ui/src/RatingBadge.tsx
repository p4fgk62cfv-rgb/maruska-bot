import { bonusGlow, ratingBadge } from '@arena/shared';
import { memo } from 'react';

export interface RatingBadgeProps {
  rating: number;
  /** Regular-player bonus streak: adds the coloured glow. */
  streak?: number;
  showValue?: boolean;
}

/** League colour, stars for every 4 levels and bars for the rest, plus progress to the next level. */
export const RatingBadge = memo(function RatingBadge({ rating, streak = 0, showValue = true }: RatingBadgeProps) {
  const badge = ratingBadge(rating);
  const glow = bonusGlow(streak);
  return (
    <span
      className={`ui-rank ui-rank--glow-${glow}`}
      style={{ ['--rank' as string]: badge.league.color }}
      title={`${badge.league.name} лига · уровень ${badge.level} · ${badge.percent}% до следующего`}
    >
      <span className="ui-rank__marks" aria-hidden="true">
        {Array.from({ length: badge.stars }, (_, i) => (
          <span key={`s${i}`} className="ui-rank__star">★</span>
        ))}
        {Array.from({ length: badge.bars }, (_, i) => (
          <span key={`b${i}`} className="ui-rank__bar" />
        ))}
        {badge.stars + badge.bars === 0 && <span className="ui-rank__dot" />}
      </span>
      {showValue && <span className="ui-rank__value">{rating.toLocaleString('ru-RU')}</span>}
      <span className="ui-rank__pct">{badge.percent}%</span>
    </span>
  );
});
