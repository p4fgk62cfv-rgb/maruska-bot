import type { CardId } from '../Card.js';
import type { GameEvent } from '../Actions.js';
import type { PlayerId } from '../GameState.js';

/**
 * Cards everyone saw going into a hand: the ones a player took from the table (and cards a caught
 * cheater got back). A careful player at the table remembers them too. A card leaves the memory
 * when its holder plays it.
 */
export type CardMemory = Record<PlayerId, CardId[]>;

export function rememberEvents(memory: CardMemory, events: readonly GameEvent[]): CardMemory {
  const next: CardMemory = {};
  for (const [id, cards] of Object.entries(memory)) next[id] = [...cards];
  const add = (id: PlayerId, cards: readonly CardId[]) => (next[id] = [...new Set([...(next[id] ?? []), ...cards])]);
  const drop = (id: PlayerId, card: CardId) => {
    if (next[id]) next[id] = next[id].filter((c) => c !== card);
  };
  for (const e of events) {
    if (e.type === 'CARDS_TAKEN') add(e.playerId, e.cards);
    else if (e.type === 'CARD_PLAYED' || e.type === 'CARD_TRANSFERRED') drop(e.playerId, e.card);
    else if (e.type === 'CHEAT_CAUGHT') for (const r of e.returned) add(r.playerId, r.cards);
  }
  return next;
}
