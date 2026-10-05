// A thread where the strong bots think, so a long search never holds up the games.
import { parentPort } from 'node:worker_threads';
import { searchMove } from '@arena/game-engine';
import type { ThinkRequest, ThinkReply } from './brain.js';

parentPort!.on('message', (req: ThinkRequest) => {
  let reply: ThinkReply;
  try {
    reply = { id: req.id, move: searchMove(req.state, req.me, req.memory, req.params, { budgetMs: req.budgetMs, iterations: req.iterations }) };
  } catch (error) {
    reply = { id: req.id, move: null, error: String(error) };
  }
  parentPort!.postMessage(reply);
});
