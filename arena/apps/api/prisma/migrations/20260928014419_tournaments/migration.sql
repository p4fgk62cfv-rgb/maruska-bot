-- CreateEnum
CREATE TYPE "MatchStatus" AS ENUM ('PENDING', 'PLAYING', 'DONE');

-- AlterTable
ALTER TABLE "tournament_players" ADD COLUMN     "eliminated_round" INTEGER;

-- CreateTable
CREATE TABLE "tournament_matches" (
    "id" UUID NOT NULL,
    "tournament_id" UUID NOT NULL,
    "round" INTEGER NOT NULL,
    "slot" INTEGER NOT NULL,
    "player_a" UUID NOT NULL,
    "player_b" UUID,
    "room_id" VARCHAR(16),
    "game_id" UUID,
    "winner_id" UUID,
    "status" "MatchStatus" NOT NULL DEFAULT 'PENDING',
    "decided_by" VARCHAR(16),
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "tournament_matches_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "tournament_matches_status_idx" ON "tournament_matches"("status");

-- CreateIndex
CREATE UNIQUE INDEX "tournament_matches_tournament_id_round_slot_key" ON "tournament_matches"("tournament_id", "round", "slot");

-- AddForeignKey
ALTER TABLE "tournament_matches" ADD CONSTRAINT "tournament_matches_tournament_id_fkey" FOREIGN KEY ("tournament_id") REFERENCES "tournaments"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- Tournament matches are played without a stake: prizes come from the entry fees.
ALTER TABLE "arena"."rooms" DROP CONSTRAINT "rooms_stake_positive";
ALTER TABLE "arena"."rooms" ADD CONSTRAINT "rooms_stake_non_negative" CHECK ("stake" >= 0);
