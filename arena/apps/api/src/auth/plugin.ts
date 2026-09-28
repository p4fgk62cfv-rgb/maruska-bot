import type { FastifyReply, FastifyRequest } from 'fastify';
import { AppError } from '../lib/errors.js';
import { readSession, type SessionClaims } from './session.js';

declare module 'fastify' {
  interface FastifyRequest {
    session: SessionClaims | null;
  }
}

export function bearerToken(request: FastifyRequest): string | null {
  const header = request.headers.authorization;
  if (!header?.startsWith('Bearer ')) return null;
  return header.slice(7).trim() || null;
}

let bans: { isBanned(userId: string): boolean } | null = null;

/** Wired once at startup so a ban also invalidates sessions already handed out. */
export function useBanList(list: { isBanned(userId: string): boolean }): void {
  bans = list;
}

/** preHandler for routes that need a logged-in player. */
export function requireSession(secret: string) {
  return async (request: FastifyRequest, _reply: FastifyReply) => {
    const token = bearerToken(request);
    const claims = token ? readSession(token, secret) : null;
    if (!claims) throw new AppError('UNAUTHORIZED');
    if (bans?.isBanned(claims.sub)) throw new AppError('BANNED');
    request.session = claims;
  };
}

export function sessionOf(request: FastifyRequest): SessionClaims {
  if (!request.session) throw new AppError('UNAUTHORIZED');
  return request.session;
}
