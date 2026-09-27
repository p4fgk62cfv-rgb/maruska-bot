import { createHmac, randomInt, scrypt, randomBytes, timingSafeEqual } from 'node:crypto';
import { promisify } from 'node:util';
import type { Random } from '@arena/game-engine';

const ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';

/** 8 characters without look-alikes (no O/0, I/1): short enough to read aloud. */
export function newRoomId(): string {
  let id = '';
  for (let i = 0; i < 8; i++) id += ALPHABET[randomInt(ALPHABET.length)];
  return id;
}

/** Invite code bound to the room: whoever has the link may skip the password. */
export function inviteCode(roomId: string, secret: string): string {
  return createHmac('sha256', secret).update(`invite:${roomId}`).digest('base64url').slice(0, 12);
}

export function checkInvite(roomId: string, code: string, secret: string): boolean {
  const expected = Buffer.from(inviteCode(roomId, secret));
  const given = Buffer.from(code);
  return expected.length === given.length && timingSafeEqual(expected, given);
}

const scryptAsync = promisify(scrypt) as (password: string, salt: Buffer, keylen: number) => Promise<Buffer>;

export async function hashPassword(password: string): Promise<string> {
  const salt = randomBytes(16);
  const hash = await scryptAsync(password, salt, 32);
  return `${salt.toString('base64url')}.${hash.toString('base64url')}`;
}

export async function verifyPassword(password: string, stored: string): Promise<boolean> {
  const [salt, hash] = stored.split('.');
  if (!salt || !hash) return false;
  const actual = await scryptAsync(password, Buffer.from(salt, 'base64url'), 32);
  const expected = Buffer.from(hash, 'base64url');
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}

/** Shuffling for live games: CSPRNG, never Math.random. */
export const cryptoRandom: Random = { int: (max) => randomInt(max) };
