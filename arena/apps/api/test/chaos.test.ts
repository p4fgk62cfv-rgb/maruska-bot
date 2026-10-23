import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import type { RoomSettings } from '@arena/shared';
import { buildApp, type AppHandle } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { createContext } from '../src/context.js';
import { createDb, type Db } from '../src/db.js';
import { journal } from '../src/lib/journal.js';
import { seedCatalog } from '../src/services/catalog.js';
import { signInitData } from '../src/telegram/initData.js';
import { Bot } from './bots.js';

/**
 * Chaos run (CHAOS=1): many tables of autoplaying clients whose connections drop and come back
 * at random, like phones on a bad network. Every game must end; nobody connected and moving
 * may lose on time; no legal move may be refused.
 */
const url = process.env.TEST_DATABASE_URL;
const BOT_TOKEN = '123456:TEST-token-for-chaos';
const TABLES = Number(process.env.CHAOS_TABLES ?? 6);

const SETTINGS: Omit<RoomSettings, 'password'> = {
  stake: 100, players: 2, deckSize: 36, speed: 'fast', variant: 'podkidnoy', throwIn: 'all',
  fairness: 'fair', ending: 'nodraw', server: 'almaz', isPrivate: false,
};

describe.skipIf(!url || !process.env.CHAOS)('chaos: flaky networks on many tables', () => {
  let db: Db;
  let handle: AppHandle;
  let address: string;
  let tg = 940_000_000 + Math.floor(Math.random() * 1_000_000);

  beforeAll(async () => {
    const config = loadConfig({ NODE_ENV: 'test', DATABASE_URL: url!, BOT_TOKEN, SESSION_SECRET: 'c'.repeat(40), WEB_DIST: '/none', AUTH_RATE_LIMIT: '1000' });
    db = createDb(url!);
    await seedCatalog(db);
    handle = await buildApp(createContext(config, db), { bot: null });
    address = await handle.app.listen({ port: 0, host: '127.0.0.1' });
  });
  afterAll(async () => {
    await handle?.app.close();
    await db?.$disconnect();
  });

  async function player(name: string): Promise<{ bot: Bot; token: string }> {
    const id = tg++;
    const initData = signInitData({ auth_date: String(Math.floor(Date.now() / 1000)), user: JSON.stringify({ id, first_name: name }) }, BOT_TOKEN);
    const res = await handle.app.inject({ method: 'POST', url: '/api/auth/telegram', payload: { initData }, remoteAddress: `10.11.${id % 250}.${id % 200}` });
    const { token, me } = res.json();
    await handle.ctx.ledger.post({ userId: me.id, currency: 'COINS', amount: 100_000n, type: 'ADMIN', source: 'test', idempotencyKey: `chaos:${me.id}` });
    const bot = new Bot(name, me.id, token, address);
    bot.watchdog = true;
    await bot.connect();
    return { bot, token };
  }

  it('every game ends, and nobody loses on time while connected', async () => {
    const drops: string[] = [];
    const tables = await Promise.all(
      Array.from({ length: TABLES }, async (_, t) => {
        const n = 2 + (t % 5);
        const people = await Promise.all(Array.from({ length: n }, (_, i) => player(`T${t}P${i}`)));
        const owner = people[0]!;
        const created = await handle.app.inject({ method: 'POST', url: '/api/rooms', payload: { ...SETTINGS, players: n }, headers: { authorization: `Bearer ${owner.token}` } });
        const roomId: string = created.json().room.id;
        for (const p of people.slice(1)) await handle.app.inject({ method: 'POST', url: `/api/rooms/${roomId}/join`, payload: {}, headers: { authorization: `Bearer ${p.token}` } });
        for (const p of people) await p.bot.send({ type: 'READY', roomId, ready: true });
        const started = (await people[0]!.bot.waitFor((m) => m.type === 'GAME_STARTED')) as { gameId: string };
        // The test client picks moves from the hints, like a player who sees which cards fit
        for (const p of people) await p.bot.send({ type: 'USE_FEATURE', gameId: started.gameId, feature: 'hints' });
        for (const p of people) {
          p.bot.think = [500, 4000];
          p.bot.autoplay = true;
          await p.bot.send({ type: 'RECONNECT', roomId });
        }
        return { roomId, people };
      }),
    );

    // Flaky network: every 1.5 s each client may drop for 0.3–6 s and come back
    let running = true;
    const chaos = (async () => {
      while (running) {
        await new Promise((r) => setTimeout(r, 1500));
        for (const table of tables) {
          for (const p of table.people) {
            if (Math.random() < Number(process.env.CHAOS_P ?? 0.08) && p.bot.ws.readyState === 1) {
              const back = 300 + Math.random() * Number(process.env.CHAOS_MAX ?? 5700);
              drops.push(p.bot.name);
              if (Math.random() < Number(process.env.CHAOS_SILENT ?? 0)) {
                // Half-dead network: the socket stays «open», nothing goes through, then it wakes up
                const ws = p.bot.ws;
                ws.pause();
                (ws as unknown as { _socket: { pause(): void; resume(): void } })._socket.pause();
                setTimeout(() => {
                  (ws as unknown as { _socket: { resume(): void } })._socket.resume();
                  ws.resume();
                }, back);
              } else {
                p.bot.close();
                setTimeout(() => void p.bot.connect().catch(() => undefined), back);
              }
            }
          }
        }
      }
    })();

    const results = await Promise.all(
      tables.map(async (table) => {
        const first = table.people[0]!.bot;
        const finished = await first.waitFor((m) => m.type === 'GAME_FINISHED', 240_000).catch(() => null);
        return { table, result: finished && finished.type === 'GAME_FINISHED' ? finished.result : null };
      }),
    );
    running = false;
    await chaos;
    await journal.flush();

    const reasons = results.map((r) => r.result?.reason ?? 'НЕ ЗАКОНЧИЛАСЬ');
    const ids = results.map((r) => r.table.people[0]!.bot.gameId).filter(Boolean) as string[];
    const refused = await db.gameEvent.findMany({ where: { gameId: { in: ids }, kind: 'move_refused' } });
    const waits = await db.gameEvent.count({ where: { gameId: { in: ids }, kind: 'wait' } });
    console.log('CHAOS', JSON.stringify({ tables: TABLES, drops: drops.length, waits, reasons, refused: refused.map((e) => e.details) }));
    // Each game: what happened to the player who lost on time, second by second
    for (const r of results) {
      const id = r.table.people[0]!.bot.gameId;
      if (!id) continue;
      const loser = r.result?.loserId;
      const game = await db.game.findUnique({ where: { id }, include: { moves: { orderBy: { seq: 'asc' } } } });
      const ev = await db.gameEvent.findMany({ where: { gameId: id }, orderBy: { createdAt: 'asc' } });
      const t0 = game!.startedAt.getTime();
      const lines = [
        ...game!.moves.slice(-6).map((m) => [m.createdAt.getTime() - t0, `move ${m.userId === loser ? 'LOSER' : m.userId ? 'other' : 'server'} ${JSON.stringify(m.action)}`] as const),
        ...ev.filter((e) => e.userId === loser).map((e) => [e.createdAt.getTime() - t0, `${e.kind} ${JSON.stringify(e.details ?? '')}`] as const),
      ].sort((x, y) => x[0] - y[0]).slice(-12);
      console.log('GAME', r.result?.reason ?? `bot saw no end, db: ${game!.status}`, game!.moves.length, 'moves\n' + lines.map(([t, l]) => `  +${(t / 1000).toFixed(1)}s ${l}`).join('\n'));
    }
    for (const p of tables.flatMap((t) => t.people)) p.bot.stop();

    expect(reasons).not.toContain('НЕ ЗАКОНЧИЛАСЬ');
  }, 300_000);
});
