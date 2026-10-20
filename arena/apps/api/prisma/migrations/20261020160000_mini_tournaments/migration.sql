-- Мини-турниры групп: один стол на вылет, приз выдаёт организатор в «Дурак Онлайн».
-- CreateEnum
CREATE TYPE "MiniTournamentStatus" AS ENUM ('RUNNING', 'FINISHED', 'CANCELLED');

-- CreateTable
CREATE TABLE "mini_tournaments" (
    "id" UUID NOT NULL,
    "chat_id" BIGINT NOT NULL,
    "title" VARCHAR(128) NOT NULL,
    "prize" BIGINT NOT NULL DEFAULT 0,
    "organizer_telegram_id" BIGINT NOT NULL,
    "organizer_name" VARCHAR(128) NOT NULL,
    "settings" JSONB NOT NULL,
    "status" "MiniTournamentStatus" NOT NULL DEFAULT 'RUNNING',
    "round" INTEGER NOT NULL DEFAULT 0,
    "room_id" VARCHAR(16),
    "winner_id" UUID,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "finished_at" TIMESTAMP(3),

    CONSTRAINT "mini_tournaments_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "mini_tournament_players" (
    "mini_id" UUID NOT NULL,
    "user_id" UUID NOT NULL,
    "telegram_id" BIGINT NOT NULL,
    "name" VARCHAR(128) NOT NULL,
    "seat" INTEGER NOT NULL,
    "place" INTEGER,
    "out_round" INTEGER,
    "out_reason" VARCHAR(16),

    CONSTRAINT "mini_tournament_players_pkey" PRIMARY KEY ("mini_id","user_id")
);

-- CreateIndex
CREATE INDEX "mini_tournaments_status_idx" ON "mini_tournaments"("status");

-- CreateIndex
CREATE INDEX "mini_tournaments_chat_id_status_idx" ON "mini_tournaments"("chat_id", "status");

-- AddForeignKey
ALTER TABLE "mini_tournament_players" ADD CONSTRAINT "mini_tournament_players_mini_id_fkey" FOREIGN KEY ("mini_id") REFERENCES "mini_tournaments"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "mini_tournament_players" ADD CONSTRAINT "mini_tournament_players_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

