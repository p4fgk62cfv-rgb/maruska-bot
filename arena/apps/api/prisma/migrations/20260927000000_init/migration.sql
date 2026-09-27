-- CreateEnum
CREATE TYPE "Currency" AS ENUM ('CREDITS', 'COINS', 'DIAMONDS');

-- CreateEnum
CREATE TYPE "TransactionType" AS ENUM ('SIGNUP_BONUS', 'DAILY_BONUS', 'GAME_STAKE', 'GAME_PAYOUT', 'GAME_REFUND', 'PURCHASE', 'TOURNAMENT_FEE', 'TOURNAMENT_PRIZE', 'ACHIEVEMENT_REWARD', 'EXCHANGE', 'ADMIN', 'MODERATION');

-- CreateEnum
CREATE TYPE "RoomStatus" AS ENUM ('WAITING', 'PLAYING', 'FINISHED', 'CLOSED');

-- CreateEnum
CREATE TYPE "GameStatus" AS ENUM ('PLAYING', 'FINISHED', 'ABORTED');

-- CreateEnum
CREATE TYPE "GameOutcome" AS ENUM ('WIN', 'LOSS', 'DRAW', 'LEFT');

-- CreateEnum
CREATE TYPE "FriendRequestStatus" AS ENUM ('PENDING', 'ACCEPTED', 'DECLINED', 'CANCELLED');

-- CreateEnum
CREATE TYPE "ItemKind" AS ENUM ('CARD_BACK', 'AVATAR', 'FRAME', 'TABLE', 'EFFECT', 'EMOJI', 'CROWN');

-- CreateEnum
CREATE TYPE "Rarity" AS ENUM ('COMMON', 'RARE', 'EPIC', 'LEGENDARY');

-- CreateEnum
CREATE TYPE "TournamentStatus" AS ENUM ('ANNOUNCED', 'REGISTRATION', 'RUNNING', 'FINISHED', 'CANCELLED');

-- CreateTable
CREATE TABLE "users" (
    "id" UUID NOT NULL,
    "telegram_id" BIGINT NOT NULL,
    "username" VARCHAR(64),
    "first_name" VARCHAR(128) NOT NULL,
    "last_name" VARCHAR(128),
    "photo_url" TEXT,
    "language_code" VARCHAR(16),
    "is_premium" BOOLEAN NOT NULL DEFAULT false,
    "banned_at" TIMESTAMP(3),
    "banned_until" TIMESTAMP(3),
    "ban_reason" VARCHAR(255),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "last_seen_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "users_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "profiles" (
    "user_id" UUID NOT NULL,
    "rating" INTEGER NOT NULL DEFAULT 0,
    "total_winnings" BIGINT NOT NULL DEFAULT 0,
    "games_played" INTEGER NOT NULL DEFAULT 0,
    "games_won" INTEGER NOT NULL DEFAULT 0,
    "games_lost" INTEGER NOT NULL DEFAULT 0,
    "games_draw" INTEGER NOT NULL DEFAULT 0,
    "win_streak" INTEGER NOT NULL DEFAULT 0,
    "best_streak" INTEGER NOT NULL DEFAULT 0,
    "premium_until" TIMESTAMP(3),
    "bonus_multiplier" INTEGER NOT NULL DEFAULT 2,
    "bonus_last_at" TIMESTAMP(3),
    "bonus_streak" INTEGER NOT NULL DEFAULT 0,
    "last_played_at" TIMESTAMP(3),
    "caught_cheating" INTEGER NOT NULL DEFAULT 0,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "profiles_pkey" PRIMARY KEY ("user_id")
);

-- CreateTable
CREATE TABLE "wallets" (
    "id" UUID NOT NULL,
    "user_id" UUID NOT NULL,
    "currency" "Currency" NOT NULL,
    "balance" BIGINT NOT NULL DEFAULT 0,
    "version" INTEGER NOT NULL DEFAULT 0,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "wallets_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "transactions" (
    "id" UUID NOT NULL,
    "wallet_id" UUID NOT NULL,
    "user_id" UUID NOT NULL,
    "currency" "Currency" NOT NULL,
    "amount" BIGINT NOT NULL,
    "balance_before" BIGINT NOT NULL,
    "balance_after" BIGINT NOT NULL,
    "type" "TransactionType" NOT NULL,
    "source" VARCHAR(128) NOT NULL,
    "idempotency_key" VARCHAR(160) NOT NULL,
    "meta" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "transactions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "rooms" (
    "id" VARCHAR(16) NOT NULL,
    "server" VARCHAR(32) NOT NULL,
    "owner_id" UUID NOT NULL,
    "status" "RoomStatus" NOT NULL DEFAULT 'WAITING',
    "is_private" BOOLEAN NOT NULL DEFAULT false,
    "password_hash" TEXT,
    "stake" BIGINT NOT NULL,
    "currency" "Currency" NOT NULL DEFAULT 'CREDITS',
    "max_players" INTEGER NOT NULL,
    "deck_size" INTEGER NOT NULL,
    "speed" VARCHAR(16) NOT NULL,
    "variant" VARCHAR(16) NOT NULL,
    "throw_in" VARCHAR(16) NOT NULL,
    "fairness" VARCHAR(16) NOT NULL,
    "ending" VARCHAR(16) NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "closed_at" TIMESTAMP(3),

    CONSTRAINT "rooms_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "games" (
    "id" UUID NOT NULL,
    "room_id" VARCHAR(16) NOT NULL,
    "status" "GameStatus" NOT NULL DEFAULT 'PLAYING',
    "stake" BIGINT NOT NULL,
    "currency" "Currency" NOT NULL DEFAULT 'CREDITS',
    "settings" JSONB NOT NULL,
    "trump_card" VARCHAR(3) NOT NULL,
    "initial_deck" TEXT[],
    "started_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "finished_at" TIMESTAMP(3),

    CONSTRAINT "games_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "game_players" (
    "game_id" UUID NOT NULL,
    "user_id" UUID NOT NULL,
    "seat" INTEGER NOT NULL,
    "place" INTEGER,
    "outcome" "GameOutcome",
    "payout" BIGINT,
    "net" BIGINT,

    CONSTRAINT "game_players_pkey" PRIMARY KEY ("game_id","user_id")
);

-- CreateTable
CREATE TABLE "game_moves" (
    "id" BIGSERIAL NOT NULL,
    "game_id" UUID NOT NULL,
    "seq" INTEGER NOT NULL,
    "user_id" UUID,
    "action" JSONB NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "game_moves_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "game_results" (
    "game_id" UUID NOT NULL,
    "kind" VARCHAR(16) NOT NULL,
    "reason" VARCHAR(32),
    "winner_id" UUID,
    "loser_id" UUID,
    "pot" BIGINT NOT NULL,
    "rake" BIGINT NOT NULL,
    "duration_ms" INTEGER NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "game_results_pkey" PRIMARY KEY ("game_id")
);

-- CreateTable
CREATE TABLE "friends" (
    "user_id" UUID NOT NULL,
    "friend_id" UUID NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "friends_pkey" PRIMARY KEY ("user_id","friend_id")
);

-- CreateTable
CREATE TABLE "friend_requests" (
    "id" UUID NOT NULL,
    "from_id" UUID NOT NULL,
    "to_id" UUID NOT NULL,
    "status" "FriendRequestStatus" NOT NULL DEFAULT 'PENDING',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "responded_at" TIMESTAMP(3),

    CONSTRAINT "friend_requests_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "items" (
    "id" UUID NOT NULL,
    "key" VARCHAR(64) NOT NULL,
    "kind" "ItemKind" NOT NULL,
    "name" VARCHAR(128) NOT NULL,
    "rarity" "Rarity" NOT NULL DEFAULT 'COMMON',
    "price" BIGINT NOT NULL DEFAULT 0,
    "currency" "Currency" NOT NULL DEFAULT 'COINS',
    "asset_url" TEXT,
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "sort_order" INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT "items_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "user_items" (
    "user_id" UUID NOT NULL,
    "item_id" UUID NOT NULL,
    "equipped" BOOLEAN NOT NULL DEFAULT false,
    "source" VARCHAR(64) NOT NULL,
    "acquired_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "user_items_pkey" PRIMARY KEY ("user_id","item_id")
);

-- CreateTable
CREATE TABLE "achievements" (
    "id" UUID NOT NULL,
    "key" VARCHAR(64) NOT NULL,
    "title" VARCHAR(128) NOT NULL,
    "description" TEXT NOT NULL,
    "icon" VARCHAR(32) NOT NULL,
    "goal" INTEGER NOT NULL DEFAULT 1,
    "reward" BIGINT NOT NULL DEFAULT 0,
    "currency" "Currency" NOT NULL DEFAULT 'COINS',
    "sort_order" INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT "achievements_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "user_achievements" (
    "user_id" UUID NOT NULL,
    "achievement_id" UUID NOT NULL,
    "progress" INTEGER NOT NULL DEFAULT 0,
    "unlocked_at" TIMESTAMP(3),

    CONSTRAINT "user_achievements_pkey" PRIMARY KEY ("user_id","achievement_id")
);

-- CreateTable
CREATE TABLE "tournaments" (
    "id" UUID NOT NULL,
    "title" VARCHAR(128) NOT NULL,
    "status" "TournamentStatus" NOT NULL DEFAULT 'ANNOUNCED',
    "entry_fee" BIGINT NOT NULL DEFAULT 0,
    "prize_pool" BIGINT NOT NULL DEFAULT 0,
    "currency" "Currency" NOT NULL DEFAULT 'CREDITS',
    "max_players" INTEGER NOT NULL,
    "settings" JSONB NOT NULL,
    "starts_at" TIMESTAMP(3) NOT NULL,
    "finished_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "tournaments_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "tournament_players" (
    "tournament_id" UUID NOT NULL,
    "user_id" UUID NOT NULL,
    "place" INTEGER,
    "prize" BIGINT,
    "joined_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "tournament_players_pkey" PRIMARY KEY ("tournament_id","user_id")
);

-- CreateTable
CREATE TABLE "notifications" (
    "id" UUID NOT NULL,
    "user_id" UUID NOT NULL,
    "kind" VARCHAR(32) NOT NULL,
    "payload" JSONB NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "sent_at" TIMESTAMP(3),
    "read_at" TIMESTAMP(3),

    CONSTRAINT "notifications_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "seasons" (
    "id" UUID NOT NULL,
    "title" VARCHAR(128) NOT NULL,
    "starts_at" TIMESTAMP(3) NOT NULL,
    "ends_at" TIMESTAMP(3) NOT NULL,
    "rewarded" BOOLEAN NOT NULL DEFAULT false,

    CONSTRAINT "seasons_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "season_ratings" (
    "season_id" UUID NOT NULL,
    "user_id" UUID NOT NULL,
    "rating" INTEGER NOT NULL DEFAULT 0,
    "wins" INTEGER NOT NULL DEFAULT 0,
    "winnings" BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT "season_ratings_pkey" PRIMARY KEY ("season_id","user_id")
);

-- CreateIndex
CREATE UNIQUE INDEX "users_telegram_id_key" ON "users"("telegram_id");

-- CreateIndex
CREATE INDEX "profiles_rating_total_winnings_games_won_idx" ON "profiles"("rating" DESC, "total_winnings" DESC, "games_won" DESC);

-- CreateIndex
CREATE UNIQUE INDEX "wallets_user_id_currency_key" ON "wallets"("user_id", "currency");

-- CreateIndex
CREATE UNIQUE INDEX "transactions_idempotency_key_key" ON "transactions"("idempotency_key");

-- CreateIndex
CREATE INDEX "transactions_user_id_created_at_idx" ON "transactions"("user_id", "created_at" DESC);

-- CreateIndex
CREATE INDEX "transactions_source_idx" ON "transactions"("source");

-- CreateIndex
CREATE INDEX "rooms_status_is_private_server_idx" ON "rooms"("status", "is_private", "server");

-- CreateIndex
CREATE INDEX "games_room_id_idx" ON "games"("room_id");

-- CreateIndex
CREATE INDEX "games_status_idx" ON "games"("status");

-- CreateIndex
CREATE INDEX "game_players_user_id_idx" ON "game_players"("user_id");

-- CreateIndex
CREATE UNIQUE INDEX "game_players_game_id_seat_key" ON "game_players"("game_id", "seat");

-- CreateIndex
CREATE UNIQUE INDEX "game_moves_game_id_seq_key" ON "game_moves"("game_id", "seq");

-- CreateIndex
CREATE INDEX "friend_requests_to_id_status_idx" ON "friend_requests"("to_id", "status");

-- CreateIndex
CREATE UNIQUE INDEX "friend_requests_from_id_to_id_key" ON "friend_requests"("from_id", "to_id");

-- CreateIndex
CREATE UNIQUE INDEX "items_key_key" ON "items"("key");

-- CreateIndex
CREATE UNIQUE INDEX "achievements_key_key" ON "achievements"("key");

-- CreateIndex
CREATE INDEX "tournaments_status_starts_at_idx" ON "tournaments"("status", "starts_at");

-- CreateIndex
CREATE INDEX "notifications_sent_at_created_at_idx" ON "notifications"("sent_at", "created_at");

-- CreateIndex
CREATE INDEX "notifications_user_id_created_at_idx" ON "notifications"("user_id", "created_at" DESC);

-- CreateIndex
CREATE INDEX "seasons_starts_at_ends_at_idx" ON "seasons"("starts_at", "ends_at");

-- CreateIndex
CREATE INDEX "season_ratings_season_id_rating_idx" ON "season_ratings"("season_id", "rating" DESC);

-- AddForeignKey
ALTER TABLE "profiles" ADD CONSTRAINT "profiles_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "wallets" ADD CONSTRAINT "wallets_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "transactions" ADD CONSTRAINT "transactions_wallet_id_fkey" FOREIGN KEY ("wallet_id") REFERENCES "wallets"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "transactions" ADD CONSTRAINT "transactions_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "rooms" ADD CONSTRAINT "rooms_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "games" ADD CONSTRAINT "games_room_id_fkey" FOREIGN KEY ("room_id") REFERENCES "rooms"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "game_players" ADD CONSTRAINT "game_players_game_id_fkey" FOREIGN KEY ("game_id") REFERENCES "games"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "game_players" ADD CONSTRAINT "game_players_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "game_moves" ADD CONSTRAINT "game_moves_game_id_fkey" FOREIGN KEY ("game_id") REFERENCES "games"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "game_moves" ADD CONSTRAINT "game_moves_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "game_results" ADD CONSTRAINT "game_results_game_id_fkey" FOREIGN KEY ("game_id") REFERENCES "games"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "friends" ADD CONSTRAINT "friends_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "friends" ADD CONSTRAINT "friends_friend_id_fkey" FOREIGN KEY ("friend_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "friend_requests" ADD CONSTRAINT "friend_requests_from_id_fkey" FOREIGN KEY ("from_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "friend_requests" ADD CONSTRAINT "friend_requests_to_id_fkey" FOREIGN KEY ("to_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "user_items" ADD CONSTRAINT "user_items_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "user_items" ADD CONSTRAINT "user_items_item_id_fkey" FOREIGN KEY ("item_id") REFERENCES "items"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "user_achievements" ADD CONSTRAINT "user_achievements_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "user_achievements" ADD CONSTRAINT "user_achievements_achievement_id_fkey" FOREIGN KEY ("achievement_id") REFERENCES "achievements"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "tournament_players" ADD CONSTRAINT "tournament_players_tournament_id_fkey" FOREIGN KEY ("tournament_id") REFERENCES "tournaments"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "tournament_players" ADD CONSTRAINT "tournament_players_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "notifications" ADD CONSTRAINT "notifications_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "season_ratings" ADD CONSTRAINT "season_ratings_season_id_fkey" FOREIGN KEY ("season_id") REFERENCES "seasons"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "season_ratings" ADD CONSTRAINT "season_ratings_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- Money invariants the ORM cannot express.
ALTER TABLE "arena"."wallets" ADD CONSTRAINT "wallets_balance_non_negative" CHECK ("balance" >= 0);
ALTER TABLE "arena"."transactions" ADD CONSTRAINT "transactions_balance_consistent" CHECK ("balance_after" = "balance_before" + "amount");
ALTER TABLE "arena"."rooms" ADD CONSTRAINT "rooms_stake_positive" CHECK ("stake" > 0);
ALTER TABLE "arena"."friends" ADD CONSTRAINT "friends_not_self" CHECK ("user_id" <> "friend_id");
ALTER TABLE "arena"."friend_requests" ADD CONSTRAINT "friend_requests_not_self" CHECK ("from_id" <> "to_id");
ALTER TABLE "arena"."profiles" ADD CONSTRAINT "profiles_bonus_range" CHECK ("bonus_multiplier" BETWEEN 1 AND 30);
