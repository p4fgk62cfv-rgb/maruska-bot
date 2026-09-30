import type { GameEvent } from '@arena/game-engine';
import { motionAllowed } from '../../lib/settings.js';

const DURATION = 340;
const EASE = 'cubic-bezier(0.22, 1, 0.36, 1)';

interface Snapshot {
  rects: Map<string, DOMRect>;
  nodes: Map<string, HTMLElement>;
}

/**
 * Card motion for the table, driven by server events.
 *
 * 1. When GAME_EVENTS arrive the DOM still shows the old state: remember where every card is.
 * 2. After the new GAME_STATE renders, each card that moved is animated from its old place
 *    (FLIP). Cards that appeared come from where they logically came from (a seat, the deck).
 * 3. Cards that left the visible area (into an opponent's hand, to the discard) are replaced
 *    by short-lived clones that fly to their destination.
 *
 * Only `translate`/`scale`/`opacity` are animated, so the GPU does the work.
 */
export class MotionDirector {
  private root: HTMLElement | null = null;
  private layer: HTMLElement | null = null;
  private snapshot: Snapshot | null = null;
  private origins = new Map<string, string>();
  private ghosts: { node: HTMLElement; from: DOMRect; to: string; delay: number }[] = [];
  private drawDelay = 0;

  attach(root: HTMLElement | null, layer: HTMLElement | null): void {
    this.root = root;
    this.layer = layer;
  }

  /** Step 1: called synchronously when events arrive, before React applies the new state. */
  prepare(events: GameEvent[], myId: string): void {
    if (!this.root || !motionAllowed()) return;
    const cards = this.root.querySelectorAll<HTMLElement>('[data-card]');
    const snapshot: Snapshot = { rects: new Map(), nodes: new Map() };
    for (const el of cards) {
      const id = el.dataset.card!;
      snapshot.rects.set(id, el.getBoundingClientRect());
      snapshot.nodes.set(id, el);
    }
    this.snapshot = snapshot;
    this.origins.clear();
    this.ghosts = [];
    this.drawDelay = 0;

    let drawIndex = 0;
    for (const event of events) {
      switch (event.type) {
        case 'CARD_PLAYED':
          if (event.playerId !== myId) this.origins.set(event.card, `[data-seat="${event.playerId}"]`);
          break;
        case 'CARD_TRANSFERRED':
          if (event.playerId !== myId) this.origins.set(event.card, `[data-seat="${event.playerId}"]`);
          break;
        case 'CARDS_TAKEN':
          if (event.playerId !== myId) for (const card of event.cards) this.leave(card, `[data-seat="${event.playerId}"]`, 0);
          break;
        case 'ROUND_FINISHED':
          if (event.outcome === 'beaten') {
            for (const [id, el] of snapshot.nodes) if (el.dataset.zone === 'table') this.leave(id, '[data-anchor="discard"]', 0);
          }
          break;
        case 'CHEAT_CAUGHT':
          for (const back of event.returned) {
            if (back.playerId !== myId) for (const card of back.cards) this.leave(card, `[data-seat="${back.playerId}"]`, 0);
          }
          break;
        case 'CARDS_DRAWN':
          // Draws go after the bout is cleared; each card leaves the stock in turn.
          for (let i = 0; i < event.count; i++, drawIndex++) {
            if (event.playerId !== myId) this.ghostFromDeck(`[data-seat="${event.playerId}"]`, 200 + drawIndex * 70);
          }
          if (event.playerId === myId) this.drawDelay = 200 + drawIndex * 70;
          break;
      }
    }
  }

  /** Step 2 + 3: called in a layout effect right after the new state rendered. */
  play(): void {
    const snapshot = this.snapshot;
    this.snapshot = null;
    if (!this.root || !snapshot || !motionAllowed()) return;

    const deck = this.anchor('[data-anchor="deck"]');
    let fresh = 0;
    for (const el of this.root.querySelectorAll<HTMLElement>('[data-card]')) {
      const id = el.dataset.card!;
      const to = el.getBoundingClientRect();
      const before = snapshot.rects.get(id);
      const originSelector = this.origins.get(id);
      const from = before ?? (originSelector ? this.anchor(originSelector) : el.dataset.zone === 'hand' ? deck : null);
      if (!from) continue;
      const delay = before ? 0 : el.dataset.zone === 'hand' ? this.drawDelay + fresh++ * 70 : 0;
      fly(el, from, to, delay);
    }

    for (const ghost of this.ghosts) {
      const target = this.anchor(ghost.to);
      if (target) this.launch(ghost.node, ghost.from, target, ghost.delay);
    }
    this.ghosts = [];
  }

  /** Opening deal: six cards to everyone, one at a time around the table. */
  deal(myId: string, seats: string[], handSize: number): void {
    if (!this.root || !motionAllowed()) return;
    const deck = this.anchor('[data-anchor="deck"]');
    if (!deck) return;
    const order = seats.length;
    const mine = [...this.root.querySelectorAll<HTMLElement>('[data-zone="hand"]')];
    for (let round = 0; round < handSize; round++) {
      seats.forEach((seat, i) => {
        const delay = (round * order + i) * 55;
        if (seat === myId) {
          const el = mine[round];
          if (el) fly(el, deck, el.getBoundingClientRect(), delay);
        } else {
          const target = this.anchor(`[data-seat="${seat}"]`);
          const back = this.root!.querySelector<HTMLElement>('[data-anchor="deck-card"]');
          if (target && back) this.launch(back.cloneNode(true) as HTMLElement, deck, target, delay);
        }
      });
    }
  }

  private leave(card: string, to: string, delay: number): void {
    const node = this.snapshot?.nodes.get(card);
    const from = this.snapshot?.rects.get(card);
    if (node && from) this.ghosts.push({ node: node.cloneNode(true) as HTMLElement, from, to, delay });
  }

  private ghostFromDeck(to: string, delay: number): void {
    const back = this.root?.querySelector<HTMLElement>('[data-anchor="deck-card"]');
    const from = back?.getBoundingClientRect();
    if (back && from) this.ghosts.push({ node: back.cloneNode(true) as HTMLElement, from, to, delay });
  }

  private anchor(selector: string): DOMRect | null {
    return this.root?.querySelector(selector)?.getBoundingClientRect() ?? null;
  }

  private launch(node: HTMLElement, from: DOMRect, to: DOMRect, delay: number): void {
    if (!this.layer) return;
    node.removeAttribute('data-card');
    node.removeAttribute('data-anchor');
    Object.assign(node.style, {
      position: 'fixed',
      left: `${from.left}px`,
      top: `${from.top}px`,
      width: `${from.width}px`,
      height: `${from.height}px`,
      margin: '0',
      transform: 'none',
      pointerEvents: 'none',
    });
    this.layer.appendChild(node);
    const dx = to.left + to.width / 2 - (from.left + from.width / 2);
    const dy = to.top + to.height / 2 - (from.top + from.height / 2);
    const scale = Math.max(0.3, to.width / from.width);
    const animation = node.animate(
      [
        { translate: '0px 0px', scale: '1', opacity: 1 },
        { translate: `${dx}px ${dy}px`, scale: `${Math.min(scale, 1)}`, opacity: 1 },
      ],
      { duration: DURATION + 60, delay, easing: EASE, fill: 'both' },
    );
    animation.onfinish = () => node.remove();
    animation.oncancel = () => node.remove();
  }
}

/** Keep only one FLIP animation per live card node; overlapping animations can make cards flicker. */
const activeFlights = new WeakMap<HTMLElement, Animation>();

/** FLIP: the element already sits at `to`; start it at `from` and let it glide home. */
export function fly(el: HTMLElement, from: DOMRect, to: DOMRect, delay: number): void {
  const dx = from.left + from.width / 2 - (to.left + to.width / 2);
  const dy = from.top + from.height / 2 - (to.top + to.height / 2);
  const scale = to.width ? from.width / to.width : 1;
  const previous = activeFlights.get(el);
  if (previous) {
    previous.cancel();
    activeFlights.delete(el);
  }
  if (Math.abs(dx) < 1 && Math.abs(dy) < 1 && Math.abs(scale - 1) < 0.01) return;
  const animation = el.animate(
    [
      { translate: `${dx}px ${dy}px`, scale: `${scale}` },
      { translate: '0px 0px', scale: '1' },
    ],
    { duration: DURATION, delay, easing: EASE, fill: 'backwards' },
  );
  activeFlights.set(el, animation);
  const clear = () => {
    if (activeFlights.get(el) === animation) activeFlights.delete(el);
  };
  animation.onfinish = clear;
  animation.oncancel = clear;
}
