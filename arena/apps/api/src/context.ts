import type { Config } from './config.js';
import type { Db } from './db.js';
import { Ledger } from './services/ledger.js';
import { MemoryPresence, type Presence } from './services/presence.js';
import { UserService } from './services/users.js';
import { WalletService } from './services/wallet.js';

/** Explicit dependency container: routes receive what they need, nothing is a hidden global. */
export interface Context {
  config: Config;
  db: Db;
  ledger: Ledger;
  users: UserService;
  presence: Presence;
  wallets: WalletService;
}

export function createContext(config: Config, db: Db): Context {
  const ledger = new Ledger(db);
  return {
    config,
    db,
    ledger,
    users: new UserService(db, ledger, config.SIGNUP_BONUS_CREDITS),
    presence: new MemoryPresence(),
    wallets: new WalletService(db, ledger),
  };
}
