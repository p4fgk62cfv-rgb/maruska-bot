import { createHmac, timingSafeEqual } from 'node:crypto';

export interface TelegramUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  language_code?: string;
  is_premium?: boolean;
  photo_url?: string;
}

export interface VerifiedInitData {
  user: TelegramUser;
  authDate: number;
  startParam: string | null;
  queryId: string | null;
}

export type InitDataFailure = 'INIT_DATA_INVALID' | 'INIT_DATA_EXPIRED';

/**
 * Checks Telegram Mini App initData as documented in
 * https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
 *
 * secret = HMAC_SHA256(key="WebAppData", msg=bot_token)
 * hash   = hex(HMAC_SHA256(key=secret, msg=data_check_string))
 */
export function verifyInitData(
  raw: string,
  botToken: string,
  maxAgeSeconds: number,
  nowSeconds = Math.floor(Date.now() / 1000),
): { ok: true; data: VerifiedInitData } | { ok: false; error: InitDataFailure } {
  if (!raw || raw.length > 8192) return { ok: false, error: 'INIT_DATA_INVALID' };

  const params = new URLSearchParams(raw);
  const hash = params.get('hash');
  if (!hash || !/^[0-9a-f]{64}$/.test(hash)) return { ok: false, error: 'INIT_DATA_INVALID' };

  const pairs: string[] = [];
  for (const [key, value] of params) {
    if (key !== 'hash') pairs.push(`${key}=${value}`);
  }
  pairs.sort();
  const checkString = pairs.join('\n');

  const secret = createHmac('sha256', 'WebAppData').update(botToken).digest();
  const expected = createHmac('sha256', secret).update(checkString).digest();
  if (!timingSafeEqual(expected, Buffer.from(hash, 'hex'))) return { ok: false, error: 'INIT_DATA_INVALID' };

  const authDate = Number(params.get('auth_date'));
  if (!Number.isInteger(authDate) || authDate <= 0) return { ok: false, error: 'INIT_DATA_INVALID' };
  if (nowSeconds - authDate > maxAgeSeconds) return { ok: false, error: 'INIT_DATA_EXPIRED' };

  let user: TelegramUser;
  try {
    user = JSON.parse(params.get('user') ?? '') as TelegramUser;
  } catch {
    return { ok: false, error: 'INIT_DATA_INVALID' };
  }
  if (!Number.isSafeInteger(user?.id) || typeof user.first_name !== 'string') {
    return { ok: false, error: 'INIT_DATA_INVALID' };
  }

  return {
    ok: true,
    data: { user, authDate, startParam: params.get('start_param'), queryId: params.get('query_id') },
  };
}

/** Builds a correctly signed initData string. Used by tests and the local dev login. */
export function signInitData(fields: Record<string, string>, botToken: string): string {
  const checkString = Object.keys(fields)
    .sort()
    .map((key) => `${key}=${fields[key]}`)
    .join('\n');
  const secret = createHmac('sha256', 'WebAppData').update(botToken).digest();
  const hash = createHmac('sha256', secret).update(checkString).digest('hex');
  return new URLSearchParams({ ...fields, hash }).toString();
}
