-- Coins for inviting a friend.
ALTER TYPE "arena"."TransactionType" ADD VALUE 'REFERRAL';

-- Referral program: every player's invite code, and who invited whom.
ALTER TABLE "arena"."users" ADD COLUMN "ref_code" VARCHAR(16);
CREATE UNIQUE INDEX "users_ref_code_key" ON "arena"."users"("ref_code");

CREATE TABLE "arena"."referrals" (
    "invitee_id" UUID NOT NULL,
    "referrer_id" UUID NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "rewarded_at" TIMESTAMP(3),
    "invitee_coins" INTEGER NOT NULL DEFAULT 0,
    "referrer_coins" INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT "referrals_pkey" PRIMARY KEY ("invitee_id")
);

CREATE INDEX "referrals_referrer_id_created_at_idx" ON "arena"."referrals"("referrer_id", "created_at");
CREATE INDEX "referrals_referrer_id_rewarded_at_idx" ON "arena"."referrals"("referrer_id", "rewarded_at");

ALTER TABLE "arena"."referrals" ADD CONSTRAINT "referrals_invitee_id_fkey" FOREIGN KEY ("invitee_id") REFERENCES "arena"."users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "arena"."referrals" ADD CONSTRAINT "referrals_referrer_id_fkey" FOREIGN KEY ("referrer_id") REFERENCES "arena"."users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
