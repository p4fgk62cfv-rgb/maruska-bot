import { EMOJI_PACKS, smilesOf, type EmojiPackKey, type ItemDto, type ItemKind } from '@arena/shared';
import { Avatar, Badge, Balance, BottomSheet, Button, Panel, PlayingCard, Tabs } from '@arena/ui';
import { useState } from 'react';
import { ApiError, api } from '../lib/api.js';
import { backOf, ringOf } from '../lib/cosmetics.js';
import { primeCache, useQuery } from '../lib/useQuery.js';
import { useNav } from '../navigation.js';
import { useMe, useSession } from '../session.js';
import { useToast } from '../toast.js';
import { QueryView, ScreenHeader } from './common.js';
import { Smile } from './game/emoji.js';

const KINDS: { value: ItemKind | 'ALL'; label: string }[] = [
  { value: 'ALL', label: 'Все' },
  { value: 'CARD_BACK', label: 'Рубашки' },
  { value: 'FRAME', label: 'Рамки' },
  { value: 'EMOJI', label: 'Смайлы' },
];
const RARITY = { COMMON: ['muted', 'Обычный'], RARE: ['cyan', 'Редкий'], EPIC: ['violet', 'Эпический'], LEGENDARY: ['gold', 'Легендарный'] } as const;
const OPTIONAL: ItemKind[] = ['FRAME', 'CROWN', 'EFFECT'];
const WEARABLE: ItemKind[] = ['CARD_BACK', 'FRAME', 'CROWN', 'EFFECT', 'EMOJI'];

/** The face of a smile pack: its first smile. */
const packIcon = (key: string) => smilesOf(key)[0]!;

function Preview({ item }: { item: ItemDto }) {
  const me = useMe();
  switch (item.kind) {
    case 'CARD_BACK':
      return <PlayingCard faceDown back={backOf(item.key)} width={64} />;
    case 'FRAME':
    case 'CROWN':
      return <Avatar id={me.id} name={me.name} photoUrl={me.photoUrl} size={48} ring={item.kind === 'FRAME' ? ringOf(item.key) : 'none'} crown={item.kind === 'CROWN'} />;
    case 'EFFECT':
      return <span className="item-effect">✦</span>;
    default:
      return <Smile smile={packIcon(item.key)} size={52} />;
  }
}

export default function ItemsScreen() {
  const query = useQuery<ItemDto[]>('/items');
  const { refreshMe } = useSession();
  const { push } = useNav();
  const toast = useToast();
  const [kind, setKind] = useState<ItemKind | 'ALL'>('ALL');
  const [busy, setBusy] = useState<string | null>(null);
  const [peek, setPeek] = useState<ItemDto | null>(null);

  const run = async (key: string, path: string, done: string) => {
    setBusy(key);
    try {
      const result = await api<unknown>(path, { method: 'POST' });
      if (Array.isArray(result)) primeCache('/items', result);
      query.reload();
      await refreshMe();
      toast(done, 'success');
    } catch (e) {
      if (e instanceof ApiError && e.code === 'INSUFFICIENT_FUNDS') {
        toast('Не хватает монет — их можно купить за звёзды', 'info');
        push('coins');
      } else toast(e instanceof ApiError ? e.message : 'Ошибка', 'error');
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="app-stack">
      <ScreenHeader title="Предметы" subtitle="Только внешний вид — на игру не влияют" />
      <button type="button" className="coin-banner" onClick={() => push('coins')}>
        <span aria-hidden="true">🪙</span>
        <span>
          <strong>Нужно больше монет?</strong>
          <small>Пакеты за звёзды Telegram</small>
        </span>
        <b>⭐ Купить</b>
      </button>
      <Tabs value={kind} onChange={setKind} items={KINDS} />
      <QueryView query={query}>
        {(items) => (
          <>
          {(kind === 'ALL' || kind === 'EMOJI') && (
            <div className="pack-list">
              {kind === 'ALL' && <h3 className="pack-list__title">Смайлы</h3>}
              {items
                .filter((i) => i.kind === 'EMOJI')
                .map((i) => (
                  <div key={i.key} className={`pack-row${i.equipped ? ' pack-row--on' : ''}`}>
                    <button type="button" className="pack-row__icon" aria-label={`Посмотреть: ${i.name}`} onClick={() => setPeek(i)}>
                      <Smile smile={packIcon(i.key)} size={44} />
                    </button>
                    <div className="pack-row__body" onClick={() => setPeek(i)}>
                      <strong>{i.name}</strong>
                      <span>{i.owned ? 'Нажмите на значок, чтобы посмотреть' : `${smilesOf(i.key).length} смайлов · для просмотра нажмите на значок`}</span>
                    </div>
                    {i.owned ? (
                      <button
                        type="button"
                        className={`pack-row__radio${i.equipped ? ' pack-row__radio--on' : ''}`}
                        aria-label={i.equipped ? 'Выбран' : 'Выбрать'}
                        disabled={i.equipped || busy === i.key}
                        onClick={() => void run(i.key, `/items/${i.key}/equip`, `Выбраны «${i.name}»`)}
                      />
                    ) : (
                      <Button size="sm" loading={busy === i.key} onClick={() => void run(i.key, `/items/${i.key}/buy`, `«${i.name}» куплены`)}>
                        <Balance kind={i.currency === 'CREDITS' ? 'credits' : 'coins'} value={i.price} />
                      </Button>
                    )}
                  </div>
                ))}
            </div>
          )}
          <div className="item-grid">
            {items
              .filter((i) => i.kind !== 'EMOJI' && (kind === 'ALL' || i.kind === kind))
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
                        <Balance kind={i.currency === 'CREDITS' ? 'credits' : 'coins'} value={i.price} />
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
          </>
        )}
      </QueryView>
      <BottomSheet open={Boolean(peek)} title={peek?.name ?? ''} onClose={() => setPeek(null)}>
        {peek && (
          <div className="app-stack">
            <div className={`emoji-grid${EMOJI_PACKS[peek.key as EmojiPackKey]?.stickers ? ' emoji-grid--stickers' : ''}`}>
              {smilesOf(peek.key).map((s) => (
                <span key={s} className="emoji-grid__cell">
                  <Smile smile={s} />
                </span>
              ))}
            </div>
            {!peek.owned ? (
              <Button block loading={busy === peek.key} onClick={() => void run(peek.key, `/items/${peek.key}/buy`, `«${peek.name}» куплены`).then(() => setPeek(null))}>
                Купить за <Balance kind={peek.currency === 'CREDITS' ? 'credits' : 'coins'} value={peek.price} />
              </Button>
            ) : !peek.equipped ? (
              <Button block variant="gold" loading={busy === peek.key} onClick={() => void run(peek.key, `/items/${peek.key}/equip`, `Выбраны «${peek.name}»`).then(() => setPeek(null))}>
                Выбрать для игры
              </Button>
            ) : (
              <p className="app-muted" style={{ textAlign: 'center' }}>Этот набор выбран — он откроется, когда нажмёте на свою аватарку за столом.</p>
            )}
          </div>
        )}
      </BottomSheet>
    </div>
  );
}
