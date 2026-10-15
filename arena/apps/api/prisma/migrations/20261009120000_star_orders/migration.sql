-- Telegram Stars: coin purchases.
ALTER TYPE "arena"."TransactionType" ADD VALUE 'STARS_PURCHASE';
ALTER TYPE "arena"."TransactionType" ADD VALUE 'STARS_REFUND';

CREATE TYPE "arena"."StarOrderStatus" AS ENUM ('PENDING', 'PAID', 'REFUNDED');

CREATE TABLE "arena"."star_orders" (
    "id" UUID NOT NULL,
    "user_id" UUID NOT NULL,
    "pack" VARCHAR(32) NOT NULL,
    "stars" INTEGER NOT NULL,
    "coins" INTEGER NOT NULL,
    "status" "arena"."StarOrderStatus" NOT NULL DEFAULT 'PENDING',
    "charge_id" VARCHAR(255),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "paid_at" TIMESTAMP(3),
    "refunded_at" TIMESTAMP(3),

    CONSTRAINT "star_orders_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "star_orders_charge_id_key" ON "arena"."star_orders"("charge_id");
CREATE INDEX "star_orders_user_id_created_at_idx" ON "arena"."star_orders"("user_id", "created_at");
CREATE INDEX "star_orders_status_created_at_idx" ON "arena"."star_orders"("status", "created_at");

ALTER TABLE "arena"."star_orders" ADD CONSTRAINT "star_orders_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "arena"."users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
