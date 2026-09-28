import { describe, expect, it } from 'vitest';
import { EMPTY_FILTER, matchesFilter, type RoomDto } from '../src/index.js';

const room = (patch: Partial<RoomDto['settings']> = {}): Pick<RoomDto, 'settings' | 'server'> => ({
  server: 'almaz',
  settings: { stake: 50_000, players: 6, deckSize: 36, speed: 'fast', variant: 'perevodnoy', throwIn: 'all', fairness: 'fair', ending: 'classic', ...patch },
});

describe('lobby filter', () => {
  it('accepts either side of a mode pair and requires every ticked pair', () => {
    const both = { ...EMPTY_FILTER, modes: ['podkidnoy', 'perevodnoy'] as const };
    expect(matchesFilter(room(), { ...both, modes: [...both.modes] })).toBe(true);
    expect(matchesFilter(room(), { ...EMPTY_FILTER, modes: ['podkidnoy'] })).toBe(false);
    expect(matchesFilter(room(), { ...EMPTY_FILTER, modes: ['perevodnoy', 'draw'] })).toBe(false);
    expect(matchesFilter(room(), { ...EMPTY_FILTER, modes: ['perevodnoy', 'all', 'fair', 'classic'] })).toBe(true);
  });

  it('keeps stakes inside the range', () => {
    const range = { ...EMPTY_FILTER, stakeMin: 10_000, stakeMax: 100_000 };
    expect(matchesFilter(room(), range)).toBe(true);
    expect(matchesFilter(room({ stake: 250_000 }), range)).toBe(false);
    expect(matchesFilter(room({ stake: 5_000 }), range)).toBe(false);
  });
});
