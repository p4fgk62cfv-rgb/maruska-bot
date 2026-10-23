import { describe, expect, it } from 'vitest';
import { TelegramBot } from '../src/services/notifier.js';

/** Telegram answers in turn with the given statuses; 429 carries «retry after 2». */
function telegram(statuses: number[]) {
  const calls: number[] = [];
  const waits: number[] = [];
  const http = (async () => {
    const status = statuses[calls.length] ?? 200;
    calls.push(status);
    if (status === 0) throw new Error('network');
    return new Response(JSON.stringify(status === 429 ? { ok: false, parameters: { retry_after: 2 } } : { ok: status === 200 }), { status });
  }) as typeof fetch;
  const bot = new TelegramBot('TOKEN', 'http://fake', http, async (ms) => void waits.push(ms));
  return { bot, calls, waits };
}

describe('TelegramBot.send', () => {
  it('a busy group: waits as long as Telegram asks and sends again', async () => {
    const { bot, calls, waits } = telegram([429, 200]);
    expect(await bot.send(-100n, { text: 'Дураком остался Лика' })).toBe('ok');
    expect(calls).toEqual([429, 200]);
    expect(waits).toEqual([2000]);
  });

  it('a network blip or a Telegram error: tries again', async () => {
    const { bot, calls } = telegram([0, 502, 200]);
    expect(await bot.send(-100n, { text: 'x' })).toBe('ok');
    expect(calls.length).toBe(3);
  });

  it('gives up after three tries, and never retries a chat that does not exist', async () => {
    const failing = telegram([502, 502, 502, 200]);
    expect(await failing.bot.send(-100n, { text: 'x' })).toBe('retry');
    expect(failing.calls.length).toBe(3);
    const blocked = telegram([403]);
    expect(await blocked.bot.send(1n, { text: 'x' })).toBe('blocked');
    expect(blocked.calls.length).toBe(1);
  });
});
