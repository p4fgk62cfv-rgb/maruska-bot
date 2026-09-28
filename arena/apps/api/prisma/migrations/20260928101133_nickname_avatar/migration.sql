-- AlterTable
ALTER TABLE "profiles" ADD COLUMN     "avatar_version" INTEGER,
ADD COLUMN     "nickname" VARCHAR(24);

-- CreateTable
CREATE TABLE "user_avatars" (
    "user_id" UUID NOT NULL,
    "mime" VARCHAR(16) NOT NULL,
    "data" BYTEA NOT NULL,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "user_avatars_pkey" PRIMARY KEY ("user_id")
);

-- AddForeignKey
ALTER TABLE "user_avatars" ADD CONSTRAINT "user_avatars_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
