/** VIP (premium) is on while its end date is ahead. */
export const isVip = (until: string | null | undefined): boolean => Boolean(until) && Date.parse(until!) > Date.now();
