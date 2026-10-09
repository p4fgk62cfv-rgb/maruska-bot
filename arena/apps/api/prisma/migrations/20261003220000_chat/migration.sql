-- The common chat of the Arena.
ALTER TABLE "arena"."profiles" ADD COLUMN "chat_muted_until" TIMESTAMP(3);

CREATE TABLE "arena"."chat_messages" (
    "id" UUID NOT NULL,
    "user_id" UUID NOT NULL,
    "text" VARCHAR(300) NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "deleted_at" TIMESTAMP(3),

    CONSTRAINT "chat_messages_pkey" PRIMARY KEY ("id")
);
CREATE INDEX "chat_messages_created_at_idx" ON "arena"."chat_messages"("created_at");
CREATE INDEX "chat_messages_user_id_created_at_idx" ON "arena"."chat_messages"("user_id", "created_at");
ALTER TABLE "arena"."chat_messages" ADD CONSTRAINT "chat_messages_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "arena"."users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

CREATE TABLE "arena"."chat_reports" (
    "message_id" UUID NOT NULL,
    "reporter_id" UUID NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "chat_reports_pkey" PRIMARY KEY ("message_id","reporter_id")
);
ALTER TABLE "arena"."chat_reports" ADD CONSTRAINT "chat_reports_message_id_fkey" FOREIGN KEY ("message_id") REFERENCES "arena"."chat_messages"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "arena"."chat_reports" ADD CONSTRAINT "chat_reports_reporter_id_fkey" FOREIGN KEY ("reporter_id") REFERENCES "arena"."users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
