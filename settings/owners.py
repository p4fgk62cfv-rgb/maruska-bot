"""
Главные админы бота — хранение в PostgreSQL (таблица bot_owners).

Проверка прав (settings.handler.is_owner) синхронная и частая, поэтому
список держится в памяти: загружается при старте и обновляется сразу
при каждом назначении или снятии.
"""

from sqlalchemy import delete, select

from database.database import session_scope
from database.models import BotOwner, User
from settings.handler import set_granted_owners


async def load() -> int:
    async with session_scope() as session:
        ids = (await session.execute(select(BotOwner.telegram_id))).scalars().all()
    set_granted_owners(ids)
    return len(ids)


async def list_all() -> list[dict]:
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(BotOwner, User.username, User.first_name)
                .outerjoin(User, User.telegram_id == BotOwner.telegram_id)
                .order_by(BotOwner.created_at)
            )
        ).all()
    return [
        {
            "id": owner.telegram_id,
            "name": first_name or owner.name or (f"@{username}" if username else str(owner.telegram_id)),
            "username": username,
            "added_by": owner.added_by,
            "created_at": owner.created_at.isoformat() if owner.created_at else None,
        }
        for owner, username, first_name in rows
    ]


async def find_user(query: str) -> dict | None:
    """Telegram ID или @username человека, который уже писал боту или был в его группах."""
    query = query.strip()
    async with session_scope() as session:
        if query.lstrip("-").isdigit():
            user = (await session.execute(select(User).where(User.telegram_id == int(query)))).scalar_one_or_none()
            if user is None:
                return {"id": int(query), "name": None, "username": None}
        else:
            name = query.lstrip("@").lower()
            if not name:
                return None
            user = (
                await session.execute(select(User).where(User.username.ilike(name)).limit(1))
            ).scalar_one_or_none()
            if user is None:
                return None
    return {"id": user.telegram_id, "name": user.first_name, "username": user.username}


async def grant(telegram_id: int, name: str | None, added_by: int) -> None:
    async with session_scope() as session:
        if await session.get(BotOwner, telegram_id) is None:
            session.add(BotOwner(telegram_id=telegram_id, name=name, added_by=added_by))
            await session.commit()
    await load()


async def revoke(telegram_id: int) -> None:
    async with session_scope() as session:
        await session.execute(delete(BotOwner).where(BotOwner.telegram_id == telegram_id))
        await session.commit()
    await load()
