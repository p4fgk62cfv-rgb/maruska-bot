import { rankValue, suitOf, type CardId, type Suit } from '../Card.js';
import type { GameEvent } from '../Actions.js';
import type { GameState, PlayerId } from '../GameState.js';

/**
 * A guess about a hidden hand, from what the table showed: «took instead of covering the 9♠ —
 * probably has no spade above 9». `conf` is how sure (0…1); the search then rarely deals such
 * cards to that player. A careful person makes the same guesses.
 */
export interface VoidNote {
  player: PlayerId;
  suit: Suit;
  /** No card of `suit` above this rank value (0: none of the suit at all). */
  above: number;
  conf: number;
}

export const violates = (card: CardId, note: VoidNote): boolean => suitOf(card) === note.suit && rankValue(card) > note.above;

const MAX_NOTES = 12;

/**
 * Updates the guesses after one action: `before` is the state the action was made in.
 * - Taking: the open cards could not (or would not) be covered — likely nothing higher of their
 *   suit, and maybe no trump. Late in the game (no stock) people rarely take what they can beat.
 * - Drawing from the stock: new unknown cards, so every guess about that hand weakens.
 * - Playing a card that contradicts a guess: the guess was wrong, it goes.
 */
export function rememberVoids(notes: readonly VoidNote[], before: GameState, events: readonly GameEvent[]): VoidNote[] {
  let out = notes.map((n) => ({ ...n }));
  const trump = before.trump.suit;
  const endgame = before.deck.length === 0;
  for (const e of events) {
    if (e.type === 'TAKE_DECLARED') {
      for (const pair of before.table) {
        if (pair.defense) continue;
        const suit = suitOf(pair.attack);
        out.push({ player: e.playerId, suit, above: rankValue(pair.attack), conf: endgame ? 0.85 : 0.6 });
        if (suit !== trump) out.push({ player: e.playerId, suit: trump, above: 0, conf: endgame ? 0.6 : 0.2 });
      }
    } else if (e.type === 'CARD_PLAYED' || e.type === 'CARD_TRANSFERRED') {
      out = out.filter((n) => n.player !== e.playerId || !violates(e.card, n));
    } else if (e.type === 'CARDS_DRAWN' && e.count > 0) {
      out = out.map((n) => (n.player === e.playerId ? { ...n, conf: n.conf * 0.5 } : n)).filter((n) => n.conf >= 0.15);
    }
  }
  // The newest guesses matter most; keep a few per player.
  const per = new Map<PlayerId, number>();
  return out
    .reverse()
    .filter((n) => {
      const k = (per.get(n.player) ?? 0) + 1;
      per.set(n.player, k);
      return k <= MAX_NOTES;
    })
    .reverse();
}
