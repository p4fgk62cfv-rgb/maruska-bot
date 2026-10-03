import { formatStake, PRACTICE_LABEL, type RoomDto } from '@arena/shared';
import { Avatar, CurrencyIcon, Icon, PlayingCard, type IconName } from '@arena/ui';
import { memo, type KeyboardEvent, type ReactNode } from 'react';
import { ringOf } from '../../lib/cosmetics.js';
import { useSettings } from '../../lib/settings.js';
import { ModeStrip } from '../lobbyParts.js';
import { Smile, type SeatSmile } from './emoji.js';

/** Top of the table: a square button on the left, the rules in the middle, the stake on the right. */
export function TableTop({
  settings,
  button,
  title,
}: {
  settings: RoomDto['settings'];
  /** `node` replaces the icon (the game's white flag). */
  button: { icon: IconName; label: string; onClick: () => void; node?: ReactNode };
  title?: string;
}) {
  const bank = settings.stake * settings.players;
  return (
    <div className="table-top">
      <button type="button" className="table-top__btn" aria-label={button.label} onClick={button.onClick}>
        {button.node ?? <Icon name={button.icon} size={24} />}
      </button>
      <div className="table-top__rules">{title ? <span className="table-top__title">{title}</span> : <ModeStrip settings={settings} />}</div>
      {settings.stake > 0 ? (
        <div className="table-top__stake">
          <span>
            {formatStake(settings.stake)} <CurrencyIcon kind="credits" size={20} />
          </span>
          <small>банк {formatStake(bank)}</small>
        </div>
      ) : (
        <div className="table-top__stake">{settings.bots ? <span className="table-top__practice">{PRACTICE_LABEL}</span> : null}</div>
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
  /** A smile over the portrait (see useSeatEmojis). */
  emoji?: SeatSmile | null;
  dim?: boolean;
  offline?: boolean;
  /** Motion anchor: cards fly to and from `[data-seat]`. */
  anchor?: boolean;
  size?: number;
  /** «Бито», «Пас», «Беру» in a speech bubble above the portrait. */
  bubble?: { text: string; tone: 'take' | 'pass' } | null;
  /** My private label about this player. */
  note?: string | null;
  /** A bot opponent: a small «бот» badge on the portrait. */
  bot?: boolean;
  onOpen?: () => void;
}

/** A player at the table: square portrait with the name on it, cards fanned behind, status below. */
export const SeatTile = memo(function SeatTile({ seat, cards = 0, back = 'classic', active, progress = null, label, number, emoji, dim, offline, anchor, size = 58, bubble, note, bot, onOpen }: SeatTileProps) {
  const fan = Math.min(cards, 7);
  return (
    <div
      className={`seat-tile${active ? ' seat-tile--active' : ''}${dim ? ' seat-tile--dim' : ''}${onOpen ? ' seat-tile--button' : ''}`}
      style={{ ['--tile' as string]: `${size}px` }}
      {...(onOpen ? { role: 'button', tabIndex: 0, 'aria-label': `Профиль: ${seat.name}`, onClick: onOpen, onKeyDown: (e: KeyboardEvent<HTMLDivElement>) => (e.key === 'Enter' || e.key === ' ') && onOpen() } : {})}
    >
      {bubble && (
        <span className={`seat-tile__bubble seat-tile__bubble--${bubble.tone}`} key={bubble.text}>
          {bubble.text}
        </span>
      )}
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
        {bot && <span className="seat-tile__bot">бот</span>}
        {cards > 0 && <span className="seat-tile__count">{cards}</span>}
        {emoji && (
          <span className="seat__emoji" key={emoji.n} aria-hidden="true">
            <Smile smile={emoji.smile} />
          </span>
        )}
      </span>
      {/* At the table the timer and the status keep their room when empty, so the felt never jumps.
          Chairs in the waiting room carry a number instead and stay compact. */}
      {(progress !== null || number === undefined) && (
        <span className={`seat-tile__timer${progress === null ? ' seat-tile__timer--idle' : ''}`} aria-hidden="true">
          {progress !== null && <span style={{ transform: `scaleX(${progress})` }} className={progress < 0.25 ? 'is-low' : undefined} />}
        </span>
      )}
      {label ? (
        <span className={`seat-tile__label seat-tile__label--${label.tone}`}>{label.text}</span>
      ) : (
        number === undefined && <span className="seat-tile__label seat-tile__label--idle" aria-hidden="true">&nbsp;</span>
      )}
      {note && <span className="seat-tile__note">{note}</span>}
      {number !== undefined && <span className="seat-tile__number">{number}</span>}
    </div>
  );
});

/** An empty chair while the room fills up. */
export function EmptySeat({ number, size = 58, onClick }: { number: number; size?: number; onClick?: () => void }) {
  const body = (
    <>
      <span className="seat-tile__frame">
        <Icon name={onClick ? 'plus' : 'hourglass'} size={size * 0.45} />
      </span>
      <span className="seat-tile__number">{number}</span>
    </>
  );
  // Before the deal a free chair can be taken with a tap.
  return onClick ? (
    <button type="button" className="seat-tile seat-tile--empty seat-tile--free" style={{ ['--tile' as string]: `${size}px` }} onClick={onClick} aria-label={`Пересесть на место ${number}`}>
      {body}
    </button>
  ) : (
    <div className="seat-tile seat-tile--empty" style={{ ['--tile' as string]: `${size}px` }}>
      {body}
    </div>
  );
}

/** Ivory dock at the bottom: the action on the left, me in the middle, extras on the right. */
export function TableDock({ actions, me, extras }: { actions: ReactNode; me: ReactNode; extras: ReactNode }) {
  const { actionRight } = useSettings();
  return (
    <div className={`table-dock${actionRight ? ' table-dock--right' : ''}`}>
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
            <CurrencyIcon kind="coins" size={13} />
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
