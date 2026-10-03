import { describe, expect, it } from 'vitest';
import { MemoryStore, ResilientStore } from '../src/realtime/store.js';
import type { GameSnapshot } from '../src/realtime/types.js';
import { Alerts } from '../src/services/alerts.js';
import type { TelegramBot } from '../src/services/notifier.js';

const quiet = { error() {}, warn() {}, info() {}, debug() {}, trace() {}, fatal() {}, child: () => quiet, level: 'silent', silent() {} } as never;

/** A store that fails while `down`, and records what landed in which order. */
class Recording extends MemoryStore {
  down = false;
  landed: string[] = [];
  override async saveGame(game: GameSnapshot) {
    if (this.down) throw new Error('down');
    this.landed.push(`${game.gameId}@${(game as unknown as { v: number }).v}`);
    return super.saveGame(game);
  }
  override async deleteGame(id: string) {
    if (this.down) throw new Error('down');
    this.landed.push(`-${id}`);
    return super.deleteGame(id);
  }
}

const snap = (id: string, v: number) => ({ gameId: id, v }) as unknown as GameSnapshot;

describe('snapshot writes survive a store outage', () => {
  it('keeps only the latest write of each game, lands them in order once the store is back, never fails the caller', async () => {
    const inner = new Recording();
    const store = new ResilientStore(inner, quiet);
    inner.down = true;
    await store.saveGame(snap('a', 1));
    await store.saveGame(snap('b', 1));
    await store.saveGame(snap('a', 2));
    await store.deleteGame('b');
    expect(store.backlog).toBe(2);
    inner.down = false;
    expect(await store.flush(1000)).toBe(true);
    expect(store.backlog).toBe(0);
    expect(inner.landed).toEqual(['a@2', '-b']);
    const { games } = await inner.loadAll();
    expect(games.map((g) => (g as unknown as { v: number }).v)).toEqual([2]);
  });

  it('a write made while it waits is a copy: later changes to the object do not leak into it', async () => {
    const inner = new Recording();
    const store = new ResilientStore(inner, quiet);
    inner.down = true;
    const game = snap('a', 1);
    await store.saveGame(game);
    (game as unknown as { v: number }).v = 99;
    inner.down = false;
    await store.flush(1000);
    expect(inner.landed).toEqual(['a@1']);
  });

  it('retries on its own and tells the owners when it is fixed', async () => {
    const inner = new Recording();
    const resolved: string[] = [];
    const alerts = new (class extends Alerts {
      override resolve(kind: string) {
        resolved.push(kind);
      }
    })(null, new Set(), quiet);
    const store = new ResilientStore(inner, quiet, alerts);
    inner.down = true;
    await store.saveGame(snap('a', 1));
    inner.down = false;
    const deadline = Date.now() + 3000;
    while (store.backlog && Date.now() < deadline) await new Promise((r) => setTimeout(r, 20));
    expect(store.backlog).toBe(0);
    expect(inner.landed).toEqual(['a@1']);
    expect(resolved).toEqual(['snapshots']);
  });
});

describe('owner alerts', () => {
  it('the same trouble reaches every owner once per window; «fixed» only follows a reported one', async () => {
    const sent: [bigint, string][] = [];
    const bot = { send: async (chat: bigint, m: { text: string }) => (sent.push([chat, m.text]), 'ok' as const) } as unknown as TelegramBot;
    const alerts = new Alerts(bot, new Set([1n, 2n]), quiet, 60_000);
    alerts.resolve('db', 'fine');
    expect(sent).toHaveLength(0);
    alerts.raise('db', 'down <b>');
    alerts.raise('db', 'down again');
    alerts.raise('redis', 'down');
    await Promise.resolve();
    expect(sent.map(([c]) => c)).toEqual([1n, 2n, 1n, 2n]);
    expect(sent[0]![1]).toContain('down &lt;b&gt;');
    alerts.resolve('db', 'fine');
    alerts.resolve('db', 'fine');
    expect(sent.filter(([, t]) => t.includes('fine'))).toHaveLength(2);
  });
});

describe('production settings', () => {
  it('refuses to start without Redis: running games would be lost on every update', async () => {
    const { loadConfig } = await import('../src/config.js');
    const env = { NODE_ENV: 'production', DATABASE_URL: 'postgresql://x', BOT_TOKEN: '1'.repeat(20), SESSION_SECRET: 's'.repeat(40) };
    expect(() => loadConfig(env)).toThrow(/REDIS_URL/);
    expect(loadConfig({ ...env, REDIS_URL: 'redis://x' }).REDIS_URL).toBe('redis://x');
  });
});
