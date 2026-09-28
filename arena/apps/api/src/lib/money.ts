/** Balances are BIGINT in Postgres but always below 2^53, so the API speaks plain numbers. */
export function toNumber(value: bigint): number {
  if (value > BigInt(Number.MAX_SAFE_INTEGER) || value < BigInt(Number.MIN_SAFE_INTEGER)) {
    throw new Error('amount exceeds safe integer range');
  }
  return Number(value);
}
