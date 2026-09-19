from sqlalchemy import select

from database.database import get_session
from database.models import User, MessageMemory


async def save_user(
    telegram_id: int,
    username: str | None,
    first_name: str | None,
):
    async for session in get_session():

        result = await session.execute(
            select(User).where(
                User.telegram_id == telegram_id
            )
        )

        user = result.scalar_one_or_none()

        if user is None:

            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
            )

            session.add(user)

        else:

            user.username = username
            user.first_name = first_name

        await session.commit()


async def save_message(
    chat_id: int,
    telegram_user_id: int,
    username: str | None,
    message: str,
):
    async for session in get_session():

        memory = MessageMemory(
            chat_id=chat_id,
            telegram_user_id=telegram_user_id,
            username=username,
            message=message,
        )

        session.add(memory)

        await session.commit()


async def get_recent_messages(
    chat_id: int,
    limit: int = 8,
):
    async for session in get_session():

        result = await session.execute(
            select(MessageMemory)
            .where(
                MessageMemory.chat_id == chat_id
            )
            .order_by(
                MessageMemory.created_at.desc()
            )
            .limit(limit)
        )

        messages = result.scalars().all()

        messages.reverse()

        return [
            f"{item.username or 'Пользователь'}: "
            f"{item.message}"
            for item in messages
        ]

    return []
