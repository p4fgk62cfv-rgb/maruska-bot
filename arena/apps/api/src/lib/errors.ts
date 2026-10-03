import { errorText, type AppErrorCode } from '@arena/shared';

const STATUS: Partial<Record<AppErrorCode, number>> = {
  UNAUTHORIZED: 401,
  INIT_DATA_INVALID: 401,
  INIT_DATA_EXPIRED: 401,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  VALIDATION_FAILED: 400,
  RATE_LIMITED: 429,
  INSUFFICIENT_FUNDS: 409,
  DUPLICATE_REQUEST: 409,
  ROOM_FULL: 409,
  SEAT_TAKEN: 409,
  ROOM_CLOSED: 410,
  GAME_ALREADY_STARTED: 409,
  WRONG_PASSWORD: 403,
  ALREADY_IN_ROOM: 409,
  MODE_NOT_SUPPORTED: 400,
  DECK_NOT_SUPPORTED: 400,
  BANNED: 403,
  FRIEND_LIMIT: 409,
  NOT_FRIENDS: 403,
  NOT_IN_ROOM: 409,
  DAILY_CREDITS_NOT_READY: 409,
  DAILY_CREDITS_BALANCE_TOO_HIGH: 409,
  REWARD_NOT_READY: 409,
  REWARD_CLAIMED: 409,
};

/** An expected failure that is safe to show to the user. Anything else becomes SERVER_ERROR. */
export class AppError extends Error {
  constructor(public readonly code: AppErrorCode, public readonly status = STATUS[code] ?? 400) {
    super(errorText(code));
    this.name = 'AppError';
  }
}
