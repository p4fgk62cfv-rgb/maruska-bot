import { formatStake, MODE_LABEL_RU, SPEED_LABEL_RU, type RoomDto } from '@arena/shared';
import { Avatar, Badge, Button, Chip } from '@arena/ui';
import type { ReactNode } from 'react';

export function modeLabels(s: RoomDto['settings']): string[] {
  const labels = [MODE_LABEL_RU[s.variant]!];
  labels.push(MODE_LABEL_RU[s.throwIn]!);
  if (s.fairness === 'cheaters') labels.push(MODE_LABEL_RU.cheaters!);
  labels.push(MODE_LABEL_RU[s.ending]!);
  return labels;
}

export function RoomCard({ room, onPlay, busy }: { room: RoomDto; onPlay: () => void; busy?: boolean }) {
  const s = room.settings;
  const free = s.players - room.seats.length;
  return (
    <div className={`room-card${room.premium ? ' room-card--premium' : ''}`}>
      <div className="room-card__stake">
        <span className="room-card__stake-value">{formatStake(s.stake)}</span>
        <span className="room-card__stake-label">ставка</span>
      </div>
      <div className="room-card__body">
        <div className="room-card__seats">
          {room.seats.map((seat) => (
            <Avatar key={seat.userId} id={seat.userId} name={seat.name} photoUrl={seat.photoUrl} size={26} />
          ))}
          {Array.from({ length: free }, (_, i) => (
            <span key={i} className="room-card__empty" />
          ))}
          <strong>
            {room.seats.length}/{s.players}
          </strong>
        </div>
        <div className="room-card__meta">
          {modeLabels(s).map((l) => (
            <span key={l}>{l}</span>
          ))}
          <span>{s.deckSize} карт</span>
          <span>{SPEED_LABEL_RU[s.speed]}</span>
        </div>
      </div>
      <div className="room-card__side">
        {room.premium && <Badge tone="gold">Премиум</Badge>}
        <Button size="sm" onClick={onPlay} loading={busy}>
          Играть
        </Button>
      </div>
    </div>
  );
}

export function ChipGroup<T extends string | number>({
  title,
  options,
  value,
  onToggle,
  render,
  disabled,
}: {
  title: string;
  options: readonly T[];
  value: readonly T[] | T;
  onToggle: (option: T) => void;
  render?: (option: T) => ReactNode;
  disabled?: (option: T) => boolean;
}) {
  const selected = (o: T) => (Array.isArray(value) ? value.includes(o) : value === o);
  return (
    <section className="chip-group">
      <h4>{title}</h4>
      <div className="chip-group__chips">
        {options.map((o) => (
          <Chip key={String(o)} selected={selected(o)} onClick={() => onToggle(o)} disabled={disabled?.(o)}>
            {render ? render(o) : String(o)}
          </Chip>
        ))}
      </div>
    </section>
  );
}
