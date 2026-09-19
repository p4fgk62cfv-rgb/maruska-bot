import os

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


# ==========================================
# DATABASE URL
# ==========================================

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    DATABASE_URL = os.getenv("DATABASE_PRIVATE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL or DATABASE_PRIVATE_URL is not set"
    )


# Убираем случайные пробелы/переносы
DATABASE_URL = DATABASE_URL.strip()


# Railway / PostgreSQL URL
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
    raise RuntimeError(
        f"Invalid PostgreSQL DATABASE_URL format: "
        f"{DATABASE_URL[:30]}"
    )


# ==========================================
# ENGINE
# ==========================================

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)


# ==========================================
# SESSION
# ==========================================

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ==========================================
# BASE
# ==========================================

class Base(DeclarativeBase):
    pass


# ==========================================
# DATABASE INITIALIZATION
# ==========================================

async def init_db():

    from database import models

    async with engine.begin() as connection:

        await connection.run_sync(
            Base.metadata.create_all
        )

    print("DATABASE: таблицы проверены/созданы")


# ==========================================
# SESSION HELPER
# ==========================================

async def get_session():

    async with SessionLocal() as session:
        yield session
