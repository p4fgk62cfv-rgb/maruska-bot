import { describe, expect, it } from 'vitest';
import { applyTimeout, createDeck, legalActions, rankValue, settle, suitOf, toPlayerView, validateSettings, type CardId } from '../src/index.js';
import { act, arranged, hand, newGame, NOW, reject } from './helpers.js';

describe('deck and deal', () => {
  it('builds 24/36/52 card decks without duplicates', () => {
    for (const size of [24, 36, 52] as const) {
      const deck = createDeck(size);
      expect(deck).toHaveLength(size);
      expect(new Set(deck).size).toBe(size);
    }
  });

  it('deals six cards to each of six players and keeps the trump as the last card', () => {
    const state = newGame({ players: 6 });
    expect(state.players.every((p) => p.hand.length === 6)).toBe(true);
    expect(state.deck).toHaveLength(0);
    expect(suitOf(state.trump.card)).toBe(state.trump.suit);
  });

  it('gives the lead to the lowest trump', () => {
    const state = newGame({ players: 4 }, 7);
    const trump = state.trump.suit;
    const holders = state.players.flatMap((p) =>
      p.hand.filter((c) => suitOf(c) === trump).map((c) => ({ id: p.id, value: rankValue(c) })),
    );
    const lowest = holders.reduce((best, h) => (h.value < best.value ? h : best));
    expect(state.attacker).toBe(lowest.id);
  });

  it('rejects unsupported settings', () => {
    expect(validateSettings({ ...newGame().rules, deckSize: 52 })).toBe('DECK_NOT_SUPPORTED');
    expect(validateSettings({ ...newGame().rules, fairness: 'cheaters' })).toBe('MODE_NOT_SUPPORTED');
    expect(validateSettings({ ...newGame().rules, players: 7 })).toBe('PLAYERS_OUT_OF_RANGE');
  });
});

describe('attack and defence', () => {
  const base = () =>
    arranged({
      trump: '6H',
      deck: ['7C', '8C', '9C', '10C'],
      hands: [
        ['7S', '7D', 'KS', 'AD', '9S', 'QC'],
        ['8S', 'QD', '6C', 'JC', '10D', 'KC'],
      ],
    });

  it('only the attacker may lead, and only with own cards', () => {
    const state = base();
    expect(reject(state, 'p2', { type: 'PLAY_CARD', card: '8S' })).toBe('NOT_YOUR_TURN');
    expect(reject(state, 'p1', { type: 'PLAY_CARD', card: '8S' })).toBe('CARD_NOT_IN_HAND');
    expect(reject(state, 'p1', { type: 'PLAY_CARD', card: 'XX' as never })).toBe('INVALID_CARD');
  });

  it('defender must beat with a higher card of the suit or a trump', () => {
    let state = act(base(), 'p1', { type: 'PLAY_CARD', card: '7S' });
    expect(state.phase).toBe('defense');
    expect(reject(state, 'p2', { type: 'PLAY_CARD', card: 'QD', target: 0 })).toBe('CARD_DOES_NOT_BEAT');
    expect(reject(state, 'p2', { type: 'PLAY_CARD', card: '8S', target: 3 })).toBe('INVALID_TARGET');
    state = act(state, 'p2', { type: 'PLAY_CARD', card: '8S', target: 0 });
    expect(state.table[0]).toMatchObject({ attack: '7S', defense: '8S' });
  });

  it('throw-ins must match a rank on the table', () => {
    let state = act(base(), 'p1', { type: 'PLAY_CARD', card: '7S' });
    expect(reject(state, 'p1', { type: 'PLAY_CARD', card: 'KS' })).toBe('RANK_NOT_ON_TABLE');
    state = act(state, 'p1', { type: 'PLAY_CARD', card: '7D' });
    expect(state.table).toHaveLength(2);
  });

  it('beaten bout goes to the discard, both refill, defender leads next', () => {
    let state = act(base(), 'p1', { type: 'PLAY_CARD', card: '7S' });
    state = act(state, 'p2', { type: 'PLAY_CARD', card: '8S', target: 0 });
    state = act(state, 'p1', { type: 'PASS' });
    expect(state.discard.sort()).toEqual(['7S', '8S']);
    expect(hand(state, 'p1')).toHaveLength(6);
    expect(hand(state, 'p2')).toHaveLength(6);
    expect(state.attacker).toBe('p2');
    expect(state.defender).toBe('p1');
    expect(state.phase).toBe('attack');
  });

  it('taking: attackers may add cards, defender collects everything and is skipped', () => {
    let state = act(base(), 'p1', { type: 'PLAY_CARD', card: '7S' });
    state = act(state, 'p2', { type: 'TAKE_CARDS' });
    expect(state.phase).toBe('taking');
    state = act(state, 'p1', { type: 'PLAY_CARD', card: '7D' });
    state = act(state, 'p1', { type: 'PASS' });
    expect(hand(state, 'p2')).toEqual(expect.arrayContaining(['7S', '7D']));
    expect(hand(state, 'p2')).toHaveLength(8);
    expect(state.attacker).toBe('p1');
  });

  it('never allows more attack cards than the defender can answer', () => {
    let state = arranged({
      trump: '6H',
      hands: [
        ['7S', '7D', '7C', 'AS'],
        ['8S', 'QD'],
      ],
    });
    state = act(state, 'p1', { type: 'PLAY_CARD', card: '7S' });
    state = act(state, 'p1', { type: 'PLAY_CARD', card: '7D' });
    expect(reject(state, 'p1', { type: 'PLAY_CARD', card: '7C' })).toBe('BOUT_LIMIT_REACHED');
    expect(legalActions(state, 'p1').attack).toEqual([]);
  });

  it('first bout is capped at five cards', () => {
    const state = arranged({
      trump: '6H',
      firstBout: true,
      deck: ['AC'],
      hands: [
        ['7S', '7D', '7C', '8S', '8D', '8C'],
        ['9S', '9D', '9C', '10S', '10D', '10C'],
      ],
    });
    expect(state.boutLimit).toBe(5);
  });
});

describe('throw-in policy', () => {
  const three = (throwIn: 'all' | 'neighbors') =>
    arranged({
      trump: '6H',
      settings: { throwIn },
      hands: [
        ['7S', 'AS'],
        ['KS', 'KD', 'KC'],
        ['7D', 'AC'],
        ['7C', 'AD'],
      ],
    });

  it('"все": any non-defender can throw in', () => {
    const state = act(three('all'), 'p1', { type: 'PLAY_CARD', card: '7S' });
    expect(legalActions(state, 'p4').attack).toEqual(['7C']);
    expect(legalActions(state, 'p3').attack).toEqual(['7D']);
  });

  it('"соседи": only the defender\'s neighbours throw in', () => {
    const state = act(three('neighbors'), 'p1', { type: 'PLAY_CARD', card: '7S' });
    expect(legalActions(state, 'p3').attack).toEqual(['7D']);
    expect(reject(state, 'p4', { type: 'PLAY_CARD', card: '7C' })).toBe('THROW_IN_NOT_ALLOWED');
  });
});

describe('transfer (переводной)', () => {
  const setup = (variant: 'podkidnoy' | 'perevodnoy', p3Hand: CardId[] = ['9C', '9D', 'AS']) =>
    arranged({
      trump: '6H',
      settings: { variant },
      hands: [
        ['7S', 'AD'],
        ['7D', 'KS', 'QC'],
        p3Hand,
      ],
    });

  it('is not available in podkidnoy', () => {
    const state = act(setup('podkidnoy'), 'p1', { type: 'PLAY_CARD', card: '7S' });
    expect(reject(state, 'p2', { type: 'TRANSFER', card: '7D' })).toBe('TRANSFER_NOT_ALLOWED');
  });

  it('passes the attack to the next player', () => {
    let state = act(setup('perevodnoy'), 'p1', { type: 'PLAY_CARD', card: '7S' });
    expect(legalActions(state, 'p2').transfer).toEqual(['7D']);
    state = act(state, 'p2', { type: 'TRANSFER', card: '7D' });
    expect(state.defender).toBe('p3');
    expect(state.attacker).toBe('p2');
    expect(state.table.map((t) => t.attack)).toEqual(['7S', '7D']);
  });

  it('is blocked when the next player cannot answer every card', () => {
    const state = act(setup('perevodnoy', ['9C']), 'p1', { type: 'PLAY_CARD', card: '7S' });
    expect(reject(state, 'p2', { type: 'TRANSFER', card: '7D' })).toBe('TRANSFER_NOT_ALLOWED');
  });

  it('is blocked once a card was beaten', () => {
    let state = arranged({
      trump: '6H',
      settings: { variant: 'perevodnoy' },
      hands: [
        ['7S', '7C', 'AD'],
        ['7D', 'KS', 'QC'],
        ['9C', '9D', 'AS'],
      ],
    });
    state = act(state, 'p1', { type: 'PLAY_CARD', card: '7S' });
    state = act(state, 'p1', { type: 'PLAY_CARD', card: '7C' });
    state = act(state, 'p2', { type: 'PLAY_CARD', card: 'KS', target: 0 });
    expect(reject(state, 'p2', { type: 'TRANSFER', card: '7D' })).toBe('TRANSFER_NOT_ALLOWED');
  });
});

describe('end of game', () => {
  it('the last player holding cards is the fool', () => {
    let state = arranged({ trump: '6H', hands: [['7S'], ['8S', '9D']] });
    state = act(state, 'p1', { type: 'PLAY_CARD', card: '7S' });
    state = act(state, 'p2', { type: 'PLAY_CARD', card: '8S', target: 0 });
    expect(state.status).toBe('finished');
    expect(state.result).toEqual({ kind: 'loser', loser: 'p2', reason: 'cards' });
    expect(state.winner).toBe('p1');
  });

  it('"ничья": both emptying their hands in the same bout is a draw', () => {
    let state = arranged({ trump: '6H', settings: { ending: 'draw' }, hands: [['7S'], ['8S']] });
    state = act(state, 'p1', { type: 'PLAY_CARD', card: '7S' });
    state = act(state, 'p2', { type: 'PLAY_CARD', card: '8S', target: 0 });
    expect(state.result).toEqual({ kind: 'draw' });
    expect(state.loser).toBeNull();
  });

  it('"классика": in the same situation the last attacker is the fool', () => {
    let state = arranged({ trump: '6H', settings: { ending: 'classic' }, hands: [['7S'], ['8S']] });
    state = act(state, 'p1', { type: 'PLAY_CARD', card: '7S' });
    state = act(state, 'p2', { type: 'PLAY_CARD', card: '8S', target: 0 });
    expect(state.result).toEqual({ kind: 'loser', loser: 'p1', reason: 'last_attack' });
    expect(state.winner).toBe('p2');
  });

  it('leaving is a forfeit', () => {
    const state = act(newGame({ players: 3 }), 'p3', { type: 'LEAVE_GAME' });
    expect(state.result).toEqual({ kind: 'loser', loser: 'p3', reason: 'left' });
    expect(reject(state, 'p1', { type: 'PASS' })).toBe('GAME_FINISHED');
  });
});

describe('timeouts', () => {
  it('an idle attacker leads the weakest card, an idle defender takes', () => {
    let state = arranged({ trump: '6H', hands: [['AH', '9S', '7D'], ['8S', 'QD', 'KC']] });
    expect(applyTimeout(state, NOW)).toBeNull();
    const deadline = state.turnDeadline ?? NOW;
    state.turnDeadline = NOW;
    let result = applyTimeout(state, NOW + 1);
    expect(result?.ok && result.state.table[0]?.attack).toBe('7D');
    state = result!.ok ? result!.state : state;
    state.turnDeadline = NOW;
    result = applyTimeout(state, NOW + 1);
    expect(result?.ok && result.state.phase).toBe('taking');
    expect(deadline).toBeGreaterThan(0);
  });
});

describe('player view', () => {
  it('hides other hands, the stock and the discard', () => {
    const state = newGame({ players: 3 });
    const view = toPlayerView(state, 'p1');
    const json = JSON.stringify(view);
    for (const other of state.players.slice(1)) for (const card of other.hand) expect(json).not.toContain(`"${card}"`);
    for (const card of state.deck.slice(0, -1)) expect(json).not.toContain(`"${card}"`);
    expect(view.you?.hand).toEqual(state.players[0]!.hand);
    expect(view.players.map((p) => p.cardCount)).toEqual([6, 6, 6]);
  });
});

describe('settlement', () => {
  it('splits the fool\'s stake minus rake between the winners', () => {
    const s = settle({ kind: 'loser', loser: 'c', reason: 'cards' }, ['a', 'b', 'c'], 1000, 10);
    expect(s.payouts).toEqual([
      { playerId: 'a', credit: 1450, net: 450 },
      { playerId: 'b', credit: 1450, net: 450 },
      { playerId: 'c', credit: 0, net: -1000 },
    ]);
    expect(s.rake).toBe(100);
    const total = s.payouts.reduce((sum, p) => sum + p.credit, 0) + s.rake;
    expect(total).toBe(3000);
  });

  it('refunds everyone on a draw', () => {
    const s = settle({ kind: 'draw' }, ['a', 'b'], 500, 10);
    expect(s.payouts.every((p) => p.credit === 500 && p.net === 0)).toBe(true);
  });
});
