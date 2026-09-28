/** Economy numbers visible to both server and client. The server is the only one that applies them. */
export const DAILY_CREDITS = {
  amount: 1450,
  /** Available only while the balance is below this. */
  belowBalance: 1450,
  cooldownMs: 24 * 3600_000,
} as const;

/** In-game extras paid with coins. Premium players get hints for free. */
export const FEATURE_PRICES = {
  /** «Вернуть карту» — per use. */
  undo: 1,
  /** «Напомнить отбой» — until the end of the game. */
  discardReminder: 2,
  /** «Подсветка» — until the end of the game. */
  hints: 3,
} as const;

export type GameFeature = keyof typeof FEATURE_PRICES;
