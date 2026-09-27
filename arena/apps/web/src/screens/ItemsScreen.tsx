import type { ItemDto, ItemKind } from '@arena/shared';
import { Badge, Balance, Panel, PlayingCard, Tabs } from '@arena/ui';
import { useState } from 'react';
import { useQuery } from '../lib/useQuery.js';
import { QueryView, ScreenHeader } from './common.js';

const KINDS: { value: ItemKind | 'ALL'; label: string }[] = [
  { value: 'ALL', label: 'Все' },
  { value: 'CARD_BACK', label: 'Рубашки' },
  { value: 'TABLE', label: 'Столы' },
  { value: 'FRAME', label: 'Рамки' },
];
const RARITY = { COMMON: ['muted', 'Обычный'], RARE: ['cyan', 'Редкий'], EPIC: ['violet', 'Эпический'], LEGENDARY: ['gold', 'Легендарный'] } as const;

export default function ItemsScreen() {
  const query = useQuery<ItemDto[]>('/items');
  const [kind, setKind] = useState<ItemKind | 'ALL'>('ALL');
  return (
    <div className="app-stack">
      <ScreenHeader title="Предметы" subtitle="Только внешний вид — на игру не влияют" />
      <Tabs value={kind} onChange={setKind} items={KINDS} />
      <QueryView query={query}>
        {(items) => (
          <div className="item-grid">
            {items
              .filter((i) => kind === 'ALL' || i.kind === kind)
              .map((i) => {
                const [tone, label] = RARITY[i.rarity];
                return (
                  <Panel key={i.key} className="item-card">
                    <div className={`item-card__preview item-card__preview--${i.kind.toLowerCase()}`}>
                      {i.kind === 'CARD_BACK' ? <PlayingCard faceDown width={46} /> : null}
                    </div>
                    <strong>{i.name}</strong>
                    <Badge tone={tone}>{label}</Badge>
                    {i.owned ? <span className="app-muted">Есть у вас</span> : <Balance kind="coins" value={i.price} />}
                  </Panel>
                );
              })}
          </div>
        )}
      </QueryView>
    </div>
  );
}
