-- Daily quests and the login calendar.
ALTER TYPE "arena"."TransactionType" ADD VALUE 'QUEST_REWARD';
ALTER TYPE "arena"."TransactionType" ADD VALUE 'LOGIN_REWARD';

ALTER TABLE "arena"."profiles" ADD COLUMN "login_day" VARCHAR(10);
ALTER TABLE "arena"."profiles" ADD COLUMN "login_step" INTEGER NOT NULL DEFAULT 0;

CREATE TABLE "arena"."daily_quests" (
    "user_id" UUID NOT NULL,
    "day" VARCHAR(10) NOT NULL,
    "key" VARCHAR(32) NOT NULL,
    "progress" INTEGER NOT NULL DEFAULT 0,
    "claimed_at" TIMESTAMP(3),

    CONSTRAINT "daily_quests_pkey" PRIMARY KEY ("user_id","day","key")
);

ALTER TABLE "arena"."daily_quests" ADD CONSTRAINT "daily_quests_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "arena"."users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
