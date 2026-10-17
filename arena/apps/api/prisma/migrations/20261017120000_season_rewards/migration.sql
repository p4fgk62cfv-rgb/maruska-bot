-- Monthly seasons pay prizes to the top players at the end.
ALTER TYPE "arena"."TransactionType" ADD VALUE IF NOT EXISTS 'SEASON_REWARD';
