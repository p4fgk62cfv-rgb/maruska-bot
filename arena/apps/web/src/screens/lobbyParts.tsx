import { formatStake, MODE_LABEL_RU, PRACTICE_LABEL, SPEED_LABEL_RU, STAKE_OPTIONS, type GameMode, type RoomDto } from '@arena/shared';
import { Avatar, CurrencyIcon, Icon, type IconName } from '@arena/ui';
import type { ReactNode } from 'react';

export const MODE_ICON: Record<GameMode, IconName> = {
  podkidnoy: 'modePodkidnoy',
  perevodnoy: 'modePerevodnoy',
  neighbors: 'modeNeighbors',
  all: 'modeAll',
  cheaters: 'modeCheaters',
  fair: 'modeFair',
  classic: 'modeClassic',
  draw: 'modeDraw',
};

export function modeLabels(s: RoomDto['settings']): string[] {
  const labels = [MODE_LABEL_RU[s.variant]!];
  labels.push(MODE_LABEL_RU[s.throwIn]!);
  if (s.fairness === 'cheaters') labels.push(MODE_LABEL_RU.cheaters!);
  labels.push(MODE_LABEL_RU[s.ending]!);
  return labels;
}

/** Speed, deck and the four modes of a table as a row of small glyphs. */
export function ModeStrip({ settings }: { settings: RoomDto['settings'] }) {
  const modes: GameMode[] = [settings.variant, settings.throwIn, settings.fairness, settings.ending];
  const title = [SPEED_LABEL_RU[settings.speed], `${settings.deckSize} карт`, ...modeLabels(settings)].join(' · ');
  return (
    <span className="mode-strip" title={title} aria-label={title}>
      <Icon name={settings.speed === 'fast' ? 'speedFast' : 'speedNormal'} size={18} />
      <span className="mode-strip__deck">{settings.deckSize}</span>
      {modes.map((m) => (
        <Icon key={m} name={MODE_ICON[m]} size={18} />
      ))}
    </span>
  );
}

/** One lobby table: who sits there, the stake, seats and rules. The whole row is the button. */
export function RoomRow({ room, onOpen, busy }: { room: RoomDto; onOpen: () => void; busy?: boolean }) {
  const s = room.settings;
  const owner = room.seats.find((seat) => seat.userId === room.ownerId) ?? room.seats[0];
  return (
    <button type="button" className={`room-row${room.premium ? ' room-row--premium' : ''}`} onClick={onOpen} disabled={busy} aria-busy={busy}>
      <span className="room-row__names">
        {room.isPrivate && <Icon name="lock" size={14} />}
        {room.isPrivate ? owner?.name ?? 'Приватный стол' : room.seats.map((seat) => seat.name).join(', ')}
      </span>
      <span className="room-row__main">
        {s.stake > 0 ? (
          <span className="room-row__stake">
            {formatStake(s.stake)}
            <CurrencyIcon kind="credits" size={22} />
          </span>
        ) : (
          <span className="room-row__stake room-row__stake--practice">{PRACTICE_LABEL}</span>
        )}
        <span className="room-row__avatars" aria-hidden="true">
          {room.seats.slice(0, 3).map((seat) => (
            <Avatar key={seat.userId} id={seat.userId} name={seat.name} photoUrl={seat.photoUrl} size={22} />
          ))}
        </span>
        <span className="room-row__seats">
          {room.seats.length}/{s.players}
          <Icon name="user" size={16} />
          {room.premium && <Icon name="crown" size={14} className="room-row__crown" />}
        </span>
        <ModeStrip settings={s} />
        <Icon name="chevron" size={18} className="room-row__go" />
      </span>
    </button>
  );
}

/** Script heading used across the felt screens. */
export function ScriptTitle({ children }: { children: ReactNode }) {
  return <h3 className="script-title">{children}</h3>;
}

/** Row of round toggles; `value` may be one option or a set. */
export function Segmented<T extends string | number>({
  options,
  value,
  onToggle,
  render,
  disabled,
  label,
}: {
  options: readonly T[];
  value: readonly T[] | T;
  onToggle: (option: T) => void;
  render?: (option: T) => ReactNode;
  disabled?: (option: T) => boolean;
  label: string;
}) {
  const on = (o: T) => (Array.isArray(value) ? value.includes(o) : value === o);
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((o) => (
        <button
          key={String(o)}
          type="button"
          className={`segmented__item${on(o) ? ' segmented__item--on' : ''}`}
          aria-pressed={on(o)}
          disabled={disabled?.(o)}
          onClick={() => onToggle(o)}
        >
          {render ? render(o) : String(o)}
        </button>
      ))}
    </div>
  );
}

const LADDER_LABELS = [0, 3, 6, 9, 12, 15].map((i) => ({ index: i, text: formatStake(STAKE_OPTIONS[i]!) }));
const LAST = STAKE_OPTIONS.length - 1;

function Ladder() {
  return (
    <div className="stake-ladder" aria-hidden="true">
      {LADDER_LABELS.map((l) => (
        <span key={l.index} style={{ left: `${(l.index / LAST) * 100}%` }}>
          {l.text}
        </span>
      ))}
    </div>
  );
}

export function stakeIndex(stake: number): number {
  const i = STAKE_OPTIONS.findIndex((s) => s >= stake);
  return i === -1 ? LAST : i;
}

/** One stake on the 100…10M ladder; steps above `max` are out of reach. */
export function StakeSlider({ value, max, onChange }: { value: number; max: number; onChange: (stake: number) => void }) {
  const reach = STAKE_OPTIONS.filter((s) => s <= max).length - 1;
  const index = stakeIndex(value);
  return (
    <div className="stake-slider">
      <div className="stake-slider__track">
        <span className="stake-slider__fill" style={{ width: `${(index / LAST) * 100}%` }} />
        {reach < LAST && <span className="stake-slider__locked" style={{ left: `${(Math.max(reach, 0) / LAST) * 100}%` }} />}
        <input
          type="range"
          min={0}
          max={LAST}
          step={1}
          value={index}
          aria-label="Ставка"
          aria-valuetext={formatStake(STAKE_OPTIONS[index]!)}
          onChange={(e) => onChange(STAKE_OPTIONS[Math.min(Number(e.target.value), Math.max(reach, 0))]!)}
        />
      </div>
      <Ladder />
    </div>
  );
}

/** A min–max stake window for the lobby filter. */
export function StakeRange({ min, max, onChange }: { min: number; max: number; onChange: (min: number, max: number) => void }) {
  const lo = stakeIndex(min);
  const hi = stakeIndex(max);
  return (
    <div className="stake-slider stake-slider--range">
      <div className="stake-slider__track">
        <span className="stake-slider__fill" style={{ left: `${(lo / LAST) * 100}%`, width: `${((hi - lo) / LAST) * 100}%` }} />
        <input
          type="range"
          min={0}
          max={LAST}
          value={lo}
          aria-label="Ставка от"
          aria-valuetext={formatStake(STAKE_OPTIONS[lo]!)}
          onChange={(e) => onChange(STAKE_OPTIONS[Math.min(Number(e.target.value), hi)]!, STAKE_OPTIONS[hi]!)}
        />
        <input
          type="range"
          min={0}
          max={LAST}
          value={hi}
          aria-label="Ставка до"
          aria-valuetext={formatStake(STAKE_OPTIONS[hi]!)}
          onChange={(e) => onChange(STAKE_OPTIONS[lo]!, STAKE_OPTIONS[Math.max(Number(e.target.value), lo)]!)}
        />
      </div>
      <Ladder />
    </div>
  );
}

/** Big square toggle with a glyph and a caption; a check mark shows it is on. */
export function CheckTile({ icon, label, on, onClick }: { icon: IconName; label: string; on: boolean; onClick: () => void }) {
  return (
    <button type="button" className={`check-tile${on ? ' check-tile--on' : ''}`} aria-pressed={on} onClick={onClick}>
      <Icon name={icon} size={34} />
      <span>{label}</span>
    </button>
  );
}
