import { describe, expect, it } from 'vitest';
import { EMPTY_FILTER, matchesFilter, type RoomDto, parseRoomStartParam, roomDeepLink } from '../src/index.js';

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

describe('room start parameter', () => {
  it('reads the room and the invite code, which may contain «_» and «-» (base64url)', () => {
    expect(parseRoomStartParam('game_AB12CD34')).toEqual({ roomId: 'AB12CD34', invite: null });
    expect(parseRoomStartParam('game_AB12CD34_aB_c-9xYz_01')).toEqual({ roomId: 'AB12CD34', invite: 'aB_c-9xYz_01' });
    expect(parseRoomStartParam(roomDeepLink('bot', 'app', 'AB12CD34', '_x_y_z-1234').split('startapp=')[1])).toEqual({ roomId: 'AB12CD34', invite: '_x_y_z-1234' });
    expect(parseRoomStartParam('ref_abc')).toBeNull();
  });
});
