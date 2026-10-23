-- Мини-турнир на два стола: столы А, Б и финал — дочерние турниры одного турнира.
-- AlterTable
ALTER TABLE "mini_tournaments" ADD COLUMN "tables" INTEGER NOT NULL DEFAULT 1,
ADD COLUMN "parent_id" UUID,
ADD COLUMN "label" VARCHAR(16);

-- CreateIndex
CREATE INDEX "mini_tournaments_parent_id_idx" ON "mini_tournaments"("parent_id");
