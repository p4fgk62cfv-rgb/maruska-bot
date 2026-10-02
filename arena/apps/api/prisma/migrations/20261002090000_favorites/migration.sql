-- CreateTable
CREATE TABLE "arena"."favorites" (
    "owner_id" UUID NOT NULL,
    "target_id" UUID NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "favorites_pkey" PRIMARY KEY ("owner_id","target_id")
);

-- AddForeignKey
ALTER TABLE "arena"."favorites" ADD CONSTRAINT "favorites_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "arena"."users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "arena"."favorites" ADD CONSTRAINT "favorites_target_id_fkey" FOREIGN KEY ("target_id") REFERENCES "arena"."users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
