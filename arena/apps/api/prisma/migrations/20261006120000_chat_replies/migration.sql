-- Replies in the common chat: a message can answer another one.
ALTER TABLE "arena"."chat_messages" ADD COLUMN "reply_to_id" UUID;
ALTER TABLE "arena"."chat_messages" ADD CONSTRAINT "chat_messages_reply_to_id_fkey" FOREIGN KEY ("reply_to_id") REFERENCES "arena"."chat_messages"("id") ON DELETE SET NULL ON UPDATE CASCADE;
