import type { PublicPlayer } from '@arena/game-engine';
import type { PlayerInfo } from '@arena/shared';
import { Avatar, RatingBadge } from '@arena/ui';
import { memo } from 'react';
import { ringOf } from '../../lib/cosmetics.js';

export interface SeatProps {
  player: PublicPlayer;
  info: PlayerInfo | undefined;
  role: 'attacker' | 'defender' | null;
  active: boolean;
  /** 0..1 of the turn time left, when this seat is on the move. */
  progress: number | null;
  passed: boolean;
  cheater: boolean;
  emoji: string | null;
  compact?: boolean;
}

const ROLE = { attacker: 'Ходит', defender: 'Отбивается' } as const;

export const Seat = memo(function Seat({ player, info, role, active, progress, passed, cheater, emoji, compact }: SeatProps) {
  const name = info?.name ?? 'Игрок';
  const status =
    player.status === 'out' ? `Вышел · ${player.place} место` : player.status === 'left' ? 'Сдался' : passed ? 'Бито' : role ? ROLE[role] : null;
  return (
    <div className={`seat${active ? ' seat--active' : ''}${compact ? ' seat--compact' : ''}${player.status !== 'active' ? ' seat--out' : ''}`}>
      <div className="seat__avatar" data-seat={player.id}>
        {progress !== null && (
          <svg className="seat__timer" viewBox="0 0 44 44" aria-hidden="true">
            <circle cx="22" cy="22" r="20" pathLength="1" style={{ strokeDashoffset: 1 - progress }} className={progress < 0.25 ? 'seat__timer--low' : ''} />
          </svg>
        )}
        <Avatar
          id={player.id}
          name={name}
          photoUrl={info?.photoUrl}
          size={compact ? 40 : 48}
          ring={ringOf(info?.frame)}
          crown={Boolean(info?.crown)}
          status={info?.connected === false ? 'offline' : undefined}
        />
        {emoji && <span className="seat__emoji">{emoji}</span>}
        {player.status === 'active' && <span className="seat__count">{player.cardCount}</span>}
      </div>
      <span className="seat__name">{name}</span>
      {info && !compact && <RatingBadge rating={info.rating} showValue={false} />}
      {status && <span className={`seat__status seat__status--${role ?? 'none'}`}>{status}</span>}
      {cheater && <span className="seat__status seat__status--cheater">Шулер</span>}
      {info?.connected === false && player.status === 'active' && <span className="seat__status seat__status--off">Нет связи</span>}
    </div>
  );
});
