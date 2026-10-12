-- VIP for Telegram Stars: an order may buy VIP days instead of coins.
ALTER TABLE "arena"."star_orders" ADD COLUMN "days" INTEGER NOT NULL DEFAULT 0;
