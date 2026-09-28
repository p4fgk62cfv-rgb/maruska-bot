import { describe, expect, it } from 'vitest';
import { readSession, issueSession } from '../src/auth/session.js';
import { signInitData, verifyInitData } from '../src/telegram/initData.js';

const TOKEN = '123456:TEST-token-for-unit-tests-only';
const now = 1_800_000_000;
const user = JSON.stringify({ id: 42, first_name: 'Стас', username: 'stas' });

describe('Telegram initData', () => {
  it('accepts correctly signed data and exposes start_param', () => {
    const raw = signInitData({ auth_date: String(now - 10), user, start_param: 'game_ABCD1234' }, TOKEN);
    const result = verifyInitData(raw, TOKEN, 3600, now);
    expect(result.ok && result.data.user.id).toBe(42);
    expect(result.ok && result.data.startParam).toBe('game_ABCD1234');
  });

  it('rejects a forged user id', () => {
    const raw = signInitData({ auth_date: String(now), user }, TOKEN);
    const forged = raw.replace(encodeURIComponent('"id":42'), encodeURIComponent('"id":43'));
    expect(forged).not.toBe(raw);
    expect(verifyInitData(forged, TOKEN, 3600, now)).toEqual({ ok: false, error: 'INIT_DATA_INVALID' });
  });

  it('rejects data signed with another bot token', () => {
    const raw = signInitData({ auth_date: String(now), user }, '999:other');
    expect(verifyInitData(raw, TOKEN, 3600, now)).toEqual({ ok: false, error: 'INIT_DATA_INVALID' });
  });

  it('rejects stale data', () => {
    const raw = signInitData({ auth_date: String(now - 7200), user }, TOKEN);
    expect(verifyInitData(raw, TOKEN, 3600, now)).toEqual({ ok: false, error: 'INIT_DATA_EXPIRED' });
  });

  it('rejects garbage', () => {
    expect(verifyInitData('', TOKEN, 3600, now).ok).toBe(false);
    expect(verifyInitData('hash=zz&user=1', TOKEN, 3600, now).ok).toBe(false);
  });
});

describe('session token', () => {
  const secret = 'x'.repeat(32);
  it('round-trips and expires', () => {
    const token = issueSession({ sub: 'u1', tg: 42, exp: 2_000_000_000 }, secret);
    expect(readSession(token, secret, 1_000)?.sub).toBe('u1');
    expect(readSession(token, secret, 2_000_000_001_000)).toBeNull();
  });
  it('rejects tampering', () => {
    const token = issueSession({ sub: 'u1', tg: 42, exp: 2_000_000_000 }, secret);
    const [payload, sig] = token.split('.');
    const evil = Buffer.from(JSON.stringify({ sub: 'u2', tg: 42, exp: 2_000_000_000 })).toString('base64url');
    expect(readSession(`${evil}.${sig}`, secret)).toBeNull();
    expect(readSession(`${payload}.${sig}`, 'y'.repeat(32))).toBeNull();
  });
});
