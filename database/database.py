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

# Дополнительная страховка:
# если Railway передаст DATABASE_PRIVATE_URL напрямую,
# тоже сможем подключиться.
if not DATABASE_URL:
    DATABASE_URL = os.getenv("DATABASE_PRIVATE_URL")


if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL or DATABASE_PRIVATE_URL is not set"
    )


# ==========================================
# POSTGRESQL + ASYNCPG
# ==========================================

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://",
        "postgresql+asyncpg://",
        1,
    )

elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://",
        "postgresql+asyncpg://",
        1,
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
    """
    Создаёт все таблицы базы данных.
    """

    # Импортируем модели здесь, чтобы они
    # успели зарегистрироваться в metadata.
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
    """
    Возвращает асинхронную сессию PostgreSQL.
    """

    async with SessionLocal() as session:
        yield session
