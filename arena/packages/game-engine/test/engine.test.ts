import { describe, expect, it } from 'vitest';
import { applyTimeout, createDeck, legalActions, rankValue, settle, suitOf, toPlayerView, undoLastMove, validateSettings, type CardId } from '../src/index.js';
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

  it('rejects impossible settings', () => {
    expect(validateSettings({ ...newGame().rules, players: 7 })).toBe('PLAYERS_OUT_OF_RANGE');
    expect(validateSettings({ ...newGame().rules, deckSize: 24, players: 5 })).toBe('DECK_TOO_SMALL');
    expect(validateSettings({ ...newGame().rules, deckSize: 24, players: 4 })).toBeNull();
    expect(validateSettings({ ...newGame().rules, deckSize: 52, players: 6 })).toBeNull();
  });

  it('deals 24- and 52-card games', () => {
    const small = newGame({ deckSize: 24, players: 4 });
    expect(small.deck).toHaveLength(0);
    expect(small.players.flatMap((p) => p.hand).every((c) => rankValue(c) >= 9)).toBe(true);
    const big = newGame({ deckSize: 52, players: 3 });
    expect(big.deck).toHaveLength(34);
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

describe('throw-in right', () => {
  const four = (throwIn: 'all' | 'neighbors') =>
    arranged({
      trump: '6H',
      settings: { throwIn },
      hands: [
        ['7S', '7H', 'AS'],
        ['KS', 'KD', 'KC', 'QS'],
        ['7D', 'AC'],
        ['7C', 'AD'],
      ],
    });

  it('the attacker throws in first; others wait for «бито»', () => {
    const state = act(four('all'), 'p1', { type: 'PLAY_CARD', card: '7S' });
    expect(legalActions(state, 'p1').canAttack).toBe(true);
    expect(reject(state, 'p3', { type: 'PLAY_CARD', card: '7D' })).toBe('THROW_IN_NOT_ALLOWED');
    expect(reject(state, 'p4', { type: 'PASS' })).toBe('CANNOT_PASS');
  });

  it('"все": after the attacker passes, every other player may throw in', () => {
    let state = act(four('all'), 'p1', { type: 'PLAY_CARD', card: '7S' });
    state = act(state, 'p1', { type: 'PASS' });
    expect(reject(state, 'p1', { type: 'PLAY_CARD', card: '7H' })).toBe('THROW_IN_NOT_ALLOWED');
    state = act(state, 'p3', { type: 'PLAY_CARD', card: '7D' });
    state = act(state, 'p4', { type: 'PLAY_CARD', card: '7C' });
    expect(state.table).toHaveLength(3);
  });

  it('"соседи": after the attacker passes, only the player after the defender may throw in', () => {
    let state = act(four('neighbors'), 'p1', { type: 'PLAY_CARD', card: '7S' });
    state = act(state, 'p1', { type: 'PASS' });
    expect(reject(state, 'p4', { type: 'PLAY_CARD', card: '7C' })).toBe('THROW_IN_NOT_ALLOWED');
    state = act(state, 'p3', { type: 'PLAY_CARD', card: '7D' });
    expect(state.table).toHaveLength(2);
  });

  it('a new rank from the defender gives the right back to the attacker', () => {
    let state = act(four('all'), 'p1', { type: 'PLAY_CARD', card: '7S' });
    state = act(state, 'p1', { type: 'PASS' });
    state = act(state, 'p2', { type: 'PLAY_CARD', card: 'KS', target: 0 });
    expect(state.passed).toEqual([]);
    expect(legalActions(state, 'p1').pass).toBe(true);
    expect(legalActions(state, 'p3').pass).toBe(false);
  });

  it('several cards of one rank can be led in one move', () => {
    const state = act(four('all'), 'p1', { type: 'PLAY_CARDS', cards: ['7S', '7H'] });
    expect(state.table.map((t) => t.attack)).toEqual(['7S', '7H']);
    expect(reject(four('all'), 'p1', { type: 'PLAY_CARDS', cards: ['7S', 'AS'] })).toBe('RANK_NOT_ON_TABLE');
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

  it('«сдаться» is a loss', () => {
    const state = act(newGame({ players: 3 }), 'p3', { type: 'LEAVE_GAME' });
    expect(state.result).toEqual({ kind: 'loser', loser: 'p3', reason: 'surrender' });
    expect(reject(state, 'p1', { type: 'PASS' })).toBe('GAME_FINISHED');
  });
});

describe('timeouts', () => {
  it('an attacker who does not lead in time loses', () => {
    const state = arranged({ trump: '6H', hands: [['AH', '9S'], ['8S', 'QD']] });
    expect(applyTimeout(state, NOW)).toBeNull();
    const result = applyTimeout({ ...state, turnDeadline: NOW }, NOW + 1);
    expect(result?.ok && result.state.result).toEqual({ kind: 'loser', loser: 'p1', reason: 'timeout' });
  });

  it('a defender who neither beats nor takes in time loses', () => {
    const state = act(arranged({ trump: '6H', hands: [['AH', '9S'], ['8S', 'QD']] }), 'p1', { type: 'PLAY_CARD', card: '9S' });
    const result = applyTimeout({ ...state, turnDeadline: NOW }, NOW + 1);
    expect(result?.ok && result.state.loser).toBe('p2');
  });

  it('throwers who do not say «бито» are passed automatically, attacker first then the rest', () => {
    let state = arranged({ trump: '6H', settings: { throwIn: 'all' }, deck: ['6C', '6D', '6S', '7C', '8C', '8D'], hands: [['9S', 'AD'], ['10S', 'KC'], ['9D', 'QC']] });
    state = act(state, 'p1', { type: 'PLAY_CARD', card: '9S' });
    state = act(state, 'p2', { type: 'PLAY_CARD', card: '10S', target: 0 });
    const result = applyTimeout({ ...state, turnDeadline: NOW }, NOW + 1);
    expect(result?.ok && result.state.status).toBe('playing');
    expect(result?.ok && result.state.discard.sort()).toEqual(['10S', '9S']);
    expect(result?.ok && result.state.attacker).toBe('p2');
  });
});

describe('«С шулерами»', () => {
  const setup = () =>
    arranged({
      trump: '6H',
      settings: { fairness: 'cheaters' },
      hands: [
        ['7S', 'QD', 'AS'],
        ['8C', '9D', 'KC'],
        ['10C', 'JC'],
      ],
    });

  it('illegal cards are accepted but not revealed to anyone', () => {
    let state = act(setup(), 'p1', { type: 'PLAY_CARD', card: '7S' });
    state = act(state, 'p2', { type: 'PLAY_CARD', card: '8C', target: 0 });
    expect(state.illegal).toHaveLength(1);
    const view = toPlayerView(state, 'p3', { hints: true });
    expect(JSON.stringify(view)).not.toContain('illegal');
  });

  it('a caught card and everything after it go back; the cheater loses the right to cheat', () => {
    let state = act(setup(), 'p1', { type: 'PLAY_CARD', card: '7S' });
    state = act(state, 'p2', { type: 'PLAY_CARD', card: '8C', target: 0 });
    const cheatSeq = state.table[0]!.defenseSeq!;
    state = act(state, 'p1', { type: 'PLAY_CARD', card: 'QD' });
    expect(reject(state, 'p3', { type: 'REPORT_CHEAT', seq: state.table[0]!.attackSeq })).toBe('NOT_ILLEGAL');
    state = act(state, 'p3', { type: 'REPORT_CHEAT', seq: cheatSeq });
    expect(state.table.map((t) => [t.attack, t.defense])).toEqual([['7S', null]]);
    expect(hand(state, 'p2')).toContain('8C');
    expect(hand(state, 'p1')).toContain('QD');
    expect(state.cheaters).toEqual(['p2']);
    expect(reject(state, 'p2', { type: 'PLAY_CARD', card: '9D', target: 0 })).toBe('CARD_DOES_NOT_BEAT');
  });

  it('is off in fair games', () => {
    const state = act(arranged({ trump: '6H', hands: [['7S'], ['8C', 'KC']] }), 'p1', { type: 'PLAY_CARD', card: '7S' });
    expect(reject(state, 'p2', { type: 'PLAY_CARD', card: '8C', target: 0 })).toBe('CARD_DOES_NOT_BEAT');
    expect(reject(state, 'p1', { type: 'REPORT_CHEAT', seq: 1 })).toBe('BAD_ACTION');
  });
});

describe('undo («вернуть карту»)', () => {
  it('takes back the last card while nobody acted after it', () => {
    const before = arranged({ trump: '6H', hands: [['7S', 'AD'], ['8S', 'QD', 'KC']] });
    const after = act(before, 'p1', { type: 'PLAY_CARD', card: 'AD' });
    const undone = undoLastMove(before, after, 'p1', NOW);
    expect(undone.ok && hand(undone.state, 'p1')).toEqual(['7S', 'AD']);
    expect(undone.ok && undone.state.version).toBe(after.version + 1);
    expect(undoLastMove(before, after, 'p2', NOW)).toEqual({ ok: false, error: 'CANNOT_UNDO' });
  });

  it('is impossible once the bout ended', () => {
    const before = act(arranged({ trump: '6H', deck: ['6C', '6D'], hands: [['7S', 'AD'], ['8S', 'QD', 'KC']] }), 'p1', { type: 'PLAY_CARD', card: '7S' });
    const beaten = act(before, 'p2', { type: 'PLAY_CARD', card: '8S', target: 0 });
    const ended = act(beaten, 'p1', { type: 'PASS' });
    expect(undoLastMove(beaten, ended, 'p1', NOW).ok).toBe(false);
  });
});

describe('player view', () => {
  it('shows playable cards only with hints on, the buttons always', () => {
    const state = act(arranged({ trump: '6H', hands: [['7S', '7D'], ['8S', 'QD']] }), 'p1', { type: 'PLAY_CARD', card: '7S' });
    const plain = toPlayerView(state, 'p2');
    expect(plain.actions.defend).toEqual({});
    expect(plain.actions.canDefend && plain.actions.take).toBe(true);
    expect(toPlayerView(state, 'p2', { hints: true }).actions.defend).toEqual({ '8S': [0] });
  });

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
