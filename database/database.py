import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://",
        "postgresql+asyncpg://",
        1,
    )
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://",
        "postgresql+asyncpg://",
        1,
    )
elif DATABASE_URL.startswith("postgresql+asyncpg://"):
    pass
else:
    scheme = DATABASE_URL.split(":", 1)[0]
    raise RuntimeError(f"Invalid DATABASE_URL scheme: {scheme}")

# asyncpg не понимает sslmode/channel_binding из строки Neon/Heroku.
parts = urlsplit(DATABASE_URL)
query = [
    (key, value)
    for key, value in parse_qsl(parts.query)
    if key not in ("sslmode", "channel_binding")
]

DATABASE_URL = urlunsplit(parts._replace(query=urlencode(query)))


engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=5,
    max_overflow=5,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    """
    Наивный UTC — колонки объявлены как DateTime без timezone.
    Замена устаревшему datetime.utcnow().
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


@asynccontextmanager
async def session_scope():
    """
    Единственный правильный способ получить сессию.

    Старый вариант `async for session in get_session()` оставлял
    асинхронный генератор незакрытым при раннем return, из-за чего
    соединения не возвращались в пул.
    """
    session = SessionLocal()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_db():
    from database import models  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

        # create_all() не добавляет колонки в уже существующие таблицы,
        # поэтому мелкие миграции делаем вручную и идемпотентно.
        migrations = (
            "ALTER TABLE users "
            "ADD COLUMN IF NOT EXISTS gender VARCHAR(20)",

            "CREATE INDEX IF NOT EXISTS ix_users_gender "
            "ON users (gender)",

            "ALTER TABLE action_images "
            "ADD COLUMN IF NOT EXISTS telegram_file_id VARCHAR(255)",

            "ALTER TABLE action_images "
            "ADD COLUMN IF NOT EXISTS fallback_url TEXT",

            "ALTER TABLE action_images "
            "ADD COLUMN IF NOT EXISTS provider VARCHAR(20) "
            "DEFAULT 'unsplash'",

            # Pixabay атрибуции не требует — снимаем NOT NULL,
            # чтобы старые колонки не мешали новым записям.
            "ALTER TABLE action_images "
            "ALTER COLUMN photographer_name DROP NOT NULL",

            "ALTER TABLE action_images "
            "ALTER COLUMN photographer_url DROP NOT NULL",

            "ALTER TABLE action_images "
            "ALTER COLUMN unsplash_url DROP NOT NULL",

            "CREATE INDEX IF NOT EXISTS ix_action_images_action_used "
            "ON action_images (action, used)",

            "CREATE INDEX IF NOT EXISTS ix_message_memory_chat_created "
            "ON message_memory (chat_id, created_at DESC)",

            "ALTER TABLE game_rounds "
            "ADD COLUMN IF NOT EXISTS token VARCHAR(64)",

            "CREATE INDEX IF NOT EXISTS ix_game_rounds_token "
            "ON game_rounds (token)",
        )

        for statement in migrations:
            await connection.execute(text(statement))

    print("DATABASE: tables checked/created")


async def close_db():
    await engine.dispose()
