import type { ItemDto, ItemKind } from '@arena/shared';
import { Avatar, Badge, Balance, Button, Panel, PlayingCard, Tabs } from '@arena/ui';
import { useState } from 'react';
import { ApiError, api } from '../lib/api.js';
import { backOf, ringOf, tableOf } from '../lib/cosmetics.js';
import { primeCache, useQuery } from '../lib/useQuery.js';
import { useMe, useSession } from '../session.js';
import { useToast } from '../toast.js';
import { QueryView, ScreenHeader } from './common.js';

const KINDS: { value: ItemKind | 'ALL'; label: string }[] = [
  { value: 'ALL', label: 'Все' },
  { value: 'CARD_BACK', label: 'Рубашки' },
  { value: 'TABLE', label: 'Столы' },
  { value: 'FRAME', label: 'Рамки' },
];
const RARITY = { COMMON: ['muted', 'Обычный'], RARE: ['cyan', 'Редкий'], EPIC: ['violet', 'Эпический'], LEGENDARY: ['gold', 'Легендарный'] } as const;
const OPTIONAL: ItemKind[] = ['FRAME', 'CROWN', 'EFFECT'];
const WEARABLE: ItemKind[] = ['CARD_BACK', 'TABLE', 'FRAME', 'CROWN', 'EFFECT'];

function Preview({ item }: { item: ItemDto }) {
  const me = useMe();
  switch (item.kind) {
    case 'CARD_BACK':
      return <PlayingCard faceDown back={backOf(item.key)} width={46} />;
    case 'TABLE':
      return <span className={`item-table item-table--${tableOf(item.key)}`} />;
    case 'FRAME':
    case 'CROWN':
      return <Avatar id={me.id} name={me.name} photoUrl={me.photoUrl} size={48} ring={item.kind === 'FRAME' ? ringOf(item.key) : 'none'} crown={item.kind === 'CROWN'} />;
    case 'EFFECT':
      return <span className="item-effect">✦</span>;
    default:
      return <span className="item-effect">😀</span>;
  }
}

export default function ItemsScreen() {
  const query = useQuery<ItemDto[]>('/items');
  const { refreshMe } = useSession();
  const toast = useToast();
  const [kind, setKind] = useState<ItemKind | 'ALL'>('ALL');
  const [busy, setBusy] = useState<string | null>(null);

  const run = async (key: string, path: string, done: string) => {
    setBusy(key);
    try {
      const result = await api<unknown>(path, { method: 'POST' });
      if (Array.isArray(result)) primeCache('/items', result);
      query.reload();
      await refreshMe();
      toast(done, 'success');
    } catch (e) {
      toast(e instanceof ApiError ? e.message : 'Ошибка', 'error');
    } finally {
      setBusy(null);
    }
  };

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
                  <Panel key={i.key} className={`item-card${i.equipped ? ' item-card--on' : ''}`}>
                    <div className="item-card__preview">
                      <Preview item={i} />
                    </div>
                    <strong>{i.name}</strong>
                    <Badge tone={tone}>{label}</Badge>
                    {!i.owned ? (
                      <Button size="sm" block loading={busy === i.key} onClick={() => void run(i.key, `/items/${i.key}/buy`, `«${i.name}» куплено`)}>
                        <Balance kind="coins" value={i.price} />
                      </Button>
                    ) : i.equipped ? (
                      OPTIONAL.includes(i.kind) ? (
                        <Button size="sm" block variant="ghost" loading={busy === i.key} onClick={() => void run(i.key, `/items/${i.key}/unequip`, 'Снято')}>
                          Снять
                        </Button>
                      ) : (
                        <Badge tone="green">Выбрано</Badge>
                      )
                    ) : WEARABLE.includes(i.kind) ? (
                      <Button size="sm" block variant="ghost" loading={busy === i.key} onClick={() => void run(i.key, `/items/${i.key}/equip`, 'Готово')}>
                        Выбрать
                      </Button>
                    ) : (
                      <Badge tone="green">Есть у вас</Badge>
                    )}
                  </Panel>
                );
              })}
          </div>
        )}
      </QueryView>
    </div>
  );
}
