-- Bot opponents
ALTER TABLE "arena"."users" ADD COLUMN "is_bot" BOOLEAN NOT NULL DEFAULT false;
CREATE INDEX "users_is_bot_idx" ON "arena"."users"("is_bot") WHERE "is_bot";
