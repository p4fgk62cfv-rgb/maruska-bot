import type { Config } from './config.js';
import type { Db } from './db.js';
import type { Realtime } from './realtime/realtime.js';
import { ItemService } from './services/items.js';
import { ModerationService } from './services/moderation.js';
import { Ledger } from './services/ledger.js';
import type { FriendService } from './services/friends.js';
import type { TournamentService } from './services/tournaments.js';
import type { Outbox } from './services/notifier.js';
import type { Presence } from './services/presence.js';
import { UserService } from './services/users.js';
import { WalletService } from './services/wallet.js';

/** Services that do not depend on the HTTP server. */
export interface BaseContext {
  config: Config;
  db: Db;
  ledger: Ledger;
  users: UserService;
  wallets: WalletService;
  items: ItemService;
  moderation: ModerationService;
}

/** Explicit dependency container: routes receive what they need, nothing is a hidden global. */
export interface Context extends BaseContext {
  realtime: Realtime;
  presence: Presence;
  outbox: Outbox;
  friends: FriendService;
  tournaments: TournamentService;
}

export function createContext(config: Config, db: Db): BaseContext {
  const ledger = new Ledger(db);
  const items = new ItemService(db, ledger);
  return {
    config,
    db,
    ledger,
    users: new UserService(db, ledger, config.SIGNUP_BONUS_CREDITS, items),
    wallets: new WalletService(db, ledger),
    items,
    moderation: new ModerationService(db, ledger),
  };
}
