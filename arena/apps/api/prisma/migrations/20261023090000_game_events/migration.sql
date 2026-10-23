-- Журнал владельца: события вокруг партий (связь, ожидания, отклонённые ходы, сообщения турниров).
-- CreateTable
CREATE TABLE "game_events" (
    "id" BIGSERIAL NOT NULL,
    "game_id" UUID,
    "room_id" VARCHAR(16),
    "mini_id" UUID,
    "user_id" UUID,
    "kind" VARCHAR(32) NOT NULL,
    "details" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "game_events_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "game_events_game_id_idx" ON "game_events"("game_id");

-- CreateIndex
CREATE INDEX "game_events_mini_id_idx" ON "game_events"("mini_id");

-- CreateIndex
CREATE INDEX "game_events_created_at_idx" ON "game_events"("created_at");
