-- CreateEnum
CREATE TYPE "ReportReason" AS ENUM ('CHEATING', 'COLLUSION', 'INSULT', 'OTHER');

-- CreateTable
CREATE TABLE "player_notes" (
    "owner_id" UUID NOT NULL,
    "target_id" UUID NOT NULL,
    "text" VARCHAR(40) NOT NULL,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "player_notes_pkey" PRIMARY KEY ("owner_id","target_id")
);

-- CreateTable
CREATE TABLE "player_reports" (
    "id" UUID NOT NULL,
    "reporter_id" UUID NOT NULL,
    "target_id" UUID NOT NULL,
    "game_id" UUID,
    "reason" "ReportReason" NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "player_reports_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "player_reports_target_id_created_at_idx" ON "player_reports"("target_id", "created_at");

-- CreateIndex
CREATE INDEX "player_reports_reporter_id_target_id_created_at_idx" ON "player_reports"("reporter_id", "target_id", "created_at");

-- AddForeignKey
ALTER TABLE "player_notes" ADD CONSTRAINT "player_notes_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "player_notes" ADD CONSTRAINT "player_notes_target_id_fkey" FOREIGN KEY ("target_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "player_reports" ADD CONSTRAINT "player_reports_reporter_id_fkey" FOREIGN KEY ("reporter_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "player_reports" ADD CONSTRAINT "player_reports_target_id_fkey" FOREIGN KEY ("target_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
