-- Sign-in outside Telegram (the installed app): the device asks, the person confirms in the bot.
CREATE TABLE "arena"."login_requests" (
    "id" VARCHAR(32) NOT NULL,
    "secret_hash" VARCHAR(64) NOT NULL,
    "device" VARCHAR(160),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "expires_at" TIMESTAMP(3) NOT NULL,
    "user_id" UUID,
    "telegram_id" BIGINT,
    "confirmed_at" TIMESTAMP(3),
    "used_at" TIMESTAMP(3),

    CONSTRAINT "login_requests_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "login_requests_expires_at_idx" ON "arena"."login_requests"("expires_at");
