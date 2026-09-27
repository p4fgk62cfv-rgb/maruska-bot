import { createHmac, timingSafeEqual } from 'node:crypto';

/**
 * Compact HS256 token: base64url(payload).base64url(signature).
 * Issued only after Telegram initData was verified; the client never picks its own id.
 */
export interface SessionClaims {
  sub: string;
  tg: number;
  exp: number;
}

function sign(payload: string, secret: string): string {
  return createHmac('sha256', secret).update(payload).digest('base64url');
}

export function issueSession(claims: SessionClaims, secret: string): string {
  const payload = Buffer.from(JSON.stringify(claims)).toString('base64url');
  return `${payload}.${sign(payload, secret)}`;
}

export function readSession(token: string, secret: string, nowMs = Date.now()): SessionClaims | null {
  const [payload, signature, extra] = token.split('.');
  if (!payload || !signature || extra !== undefined) return null;

  const expected = Buffer.from(sign(payload, secret));
  const given = Buffer.from(signature);
  if (expected.length !== given.length || !timingSafeEqual(expected, given)) return null;

  try {
    const claims = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8')) as SessionClaims;
    if (typeof claims.sub !== 'string' || typeof claims.exp !== 'number') return null;
    return claims.exp * 1000 > nowMs ? claims : null;
  } catch {
    return null;
  }
}
