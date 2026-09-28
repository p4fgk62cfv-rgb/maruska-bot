import { formatStake, type RoomDto } from '@arena/shared';
import { Avatar, Icon, PlayingCard, type IconName } from '@arena/ui';
import { memo, type ReactNode } from 'react';
import { ringOf } from '../../lib/cosmetics.js';
import { ModeStrip } from '../lobbyParts.js';

/** Top of the table: a square button on the left, the rules in the middle, the stake on the right. */
export function TableTop({
  settings,
  button,
  title,
}: {
  settings: RoomDto['settings'];
  button: { icon: IconName; label: string; onClick: () => void };
  title?: string;
}) {
  const bank = settings.stake * settings.players;
  return (
    <div className="table-top">
      <button type="button" className="table-top__btn" aria-label={button.label} onClick={button.onClick}>
        <Icon name={button.icon} size={24} />
      </button>
      <div className="table-top__rules">{title ? <span className="table-top__title">{title}</span> : <ModeStrip settings={settings} />}</div>
      {settings.stake > 0 ? (
        <div className="table-top__stake">
          <span>
            {formatStake(settings.stake)} <Icon name="chip" size={18} />
          </span>
          <small>банк {formatStake(bank)}</small>
        </div>
      ) : (
        <div className="table-top__stake" />
      )}
    </div>
  );
}

export interface TileSeat {
  id: string;
  name: string;
  photoUrl: string | null;
  frame: string | null;
  crown: string | null;
}

export interface SeatTileProps {
  seat: TileSeat;
  /** Face-down cards fanned behind the tile (opponents during a game). */
  cards?: number;
  back?: string;
  active?: boolean;
  /** 0..1 of the turn time left while this seat is on the move. */
  progress?: number | null;
  label?: { text: string; tone: 'attack' | 'defend' | 'muted' | 'alert' | 'ready' } | null;
  number?: number;
  emoji?: string | null;
  dim?: boolean;
  offline?: boolean;
  /** Motion anchor: cards fly to and from `[data-seat]`. */
  anchor?: boolean;
  size?: number;
}

/** A player at the table: square portrait with the name on it, cards fanned behind, status below. */
export const SeatTile = memo(function SeatTile({ seat, cards = 0, back = 'classic', active, progress = null, label, number, emoji, dim, offline, anchor, size = 58 }: SeatTileProps) {
  const fan = Math.min(cards, 7);
  return (
    <div className={`seat-tile${active ? ' seat-tile--active' : ''}${dim ? ' seat-tile--dim' : ''}`} style={{ ['--tile' as string]: `${size}px` }}>
      {fan > 0 && (
        <span className="seat-tile__fan" aria-hidden="true">
          {Array.from({ length: fan }, (_, i) => (
            <span key={i} style={{ rotate: `${(i - (fan - 1) / 2) * 11}deg` }}>
              <PlayingCard faceDown back={back} width={size * 0.5} />
            </span>
          ))}
        </span>
      )}
      <span className="seat-tile__frame" {...(anchor ? { 'data-seat': seat.id } : {})}>
        <Avatar id={seat.id} name={seat.name} photoUrl={seat.photoUrl} size={size} ring={ringOf(seat.frame)} crown={Boolean(seat.crown)} status={offline ? 'offline' : undefined} />
        <span className="seat-tile__name">{seat.name}</span>
        {cards > 0 && <span className="seat-tile__count">{cards}</span>}
        {emoji && <span className="seat__emoji">{emoji}</span>}
      </span>
      {progress !== null && (
        <span className="seat-tile__timer" aria-hidden="true">
          <span style={{ transform: `scaleX(${progress})` }} className={progress < 0.25 ? 'is-low' : undefined} />
        </span>
      )}
      {label && <span className={`seat-tile__label seat-tile__label--${label.tone}`}>{label.text}</span>}
      {number !== undefined && <span className="seat-tile__number">{number}</span>}
    </div>
  );
});

/** An empty chair while the room fills up. */
export function EmptySeat({ number, size = 58 }: { number: number; size?: number }) {
  return (
    <div className="seat-tile seat-tile--empty" style={{ ['--tile' as string]: `${size}px` }}>
      <span className="seat-tile__frame">
        <Icon name="hourglass" size={size * 0.45} />
      </span>
      <span className="seat-tile__number">{number}</span>
    </div>
  );
}

/** Ivory dock at the bottom: the action on the left, me in the middle, extras on the right. */
export function TableDock({ actions, me, extras }: { actions: ReactNode; me: ReactNode; extras: ReactNode }) {
  return (
    <div className="table-dock">
      <div className="table-dock__actions">{actions}</div>
      <div className="table-dock__me">{me}</div>
      <div className="table-dock__extras">{extras}</div>
    </div>
  );
}

/** Big ivory pill with a handwritten verb: «Беру», «Бито», «Готов». */
export function DockAction({ children, onClick, busy, tone = 'main', disabled }: { children: ReactNode; onClick: () => void; busy?: boolean; tone?: 'main' | 'alt' | 'gold'; disabled?: boolean }) {
  return (
    <button type="button" className={`dock-action dock-action--${tone}`} onClick={onClick} disabled={busy || disabled} aria-busy={busy}>
      {children}
    </button>
  );
}

/** Paid helper with its coin price above it. */
export function DockExtra({ icon, label, price, on, onClick, disabled }: { icon: IconName; label: string; price: number | null; on?: boolean; onClick: () => void; disabled?: boolean }) {
  return (
    <button type="button" className={`dock-extra${on ? ' dock-extra--on' : ''}`} onClick={onClick} disabled={disabled} aria-label={label} title={label}>
      <span className="dock-extra__price">
        {price !== null ? (
          <>
            {price}
            <Icon name="coin" size={12} />
          </>
        ) : (
          '✓'
        )}
      </span>
      <span className="dock-extra__icon">
        <Icon name={icon} size={24} />
      </span>
    </button>
  );
}
