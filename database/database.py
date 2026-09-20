import os
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

parts = urlsplit(DATABASE_URL)
query = [
    (key, value)
    for key, value in parse_qsl(parts.query)
    if key not in ("sslmode", "channel_binding")
]

DATABASE_URL = urlunsplit(
    parts._replace(query=urlencode(query))
)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=1800,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def init_db():
    from database import models  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

        # create_all() не добавляет новые колонки в уже существующие таблицы.
        # Поэтому для gender делаем безопасную миграцию.
        await connection.execute(
            text(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS gender VARCHAR(20)"
            )
        )

        await connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_users_gender "
                "ON users (gender)"
            )
        )

    print("DATABASE: tables checked/created")


async def get_session():
    async with SessionLocal() as session:
        yield session
