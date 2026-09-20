from datetime import datetime

from sqlalchemy import select, desc

from database.database import get_session
from database.models import (
    User,
    UserProfile,
    UserFact,
    MessageMemory,
    GroupMember,
)


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

        # Глобальный профиль
        profile_result = await session.execute(
            select(UserProfile).where(
                UserProfile.telegram_id == telegram_user_id
            )
        )

        profile = profile_result.scalar_one_or_none()

        if profile is None:

            profile = UserProfile(
                telegram_id=telegram_user_id,
                display_name=username,
                messages_count=1,
            )

            session.add(profile)

        else:

            profile.display_name = username
            profile.messages_count += 1
            profile.updated_at = datetime.utcnow()

        # Профиль участника конкретной группы
        member_result = await session.execute(
            select(GroupMember).where(
                GroupMember.chat_id == chat_id,
                GroupMember.telegram_id == telegram_user_id,
            )
        )

        member = member_result.scalar_one_or_none()

        if member is None:

            member = GroupMember(
                chat_id=chat_id,
                telegram_id=telegram_user_id,
                display_name=username,
                messages_count=1,
            )

            session.add(member)

        else:

            member.display_name = username
            member.messages_count += 1
            member.updated_at = datetime.utcnow()

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


async def get_profile(
    telegram_id: int,
):
    async for session in get_session():

        result = await session.execute(
            select(UserProfile).where(
                UserProfile.telegram_id == telegram_id
            )
        )

        return result.scalar_one_or_none()

    return None


async def create_profile_if_needed(
    telegram_id: int,
    display_name: str | None,
):
    async for session in get_session():

        result = await session.execute(
            select(UserProfile).where(
                UserProfile.telegram_id == telegram_id
            )
        )

        profile = result.scalar_one_or_none()

        if profile is None:

            profile = UserProfile(
                telegram_id=telegram_id,
                display_name=display_name,
            )

            session.add(profile)

            await session.commit()

        return profile

    return None


async def add_fact(
    telegram_id: int,
    fact: str,
):
    async for session in get_session():

        new_fact = UserFact(
            telegram_id=telegram_id,
            fact=fact,
        )

        session.add(new_fact)

        await session.commit()


async def get_facts(
    telegram_id: int,
    limit: int = 20,
):
    async for session in get_session():

        result = await session.execute(
            select(UserFact)
            .where(
                UserFact.telegram_id == telegram_id
            )
            .order_by(
                UserFact.created_at.desc()
            )
            .limit(limit)
        )

        facts = result.scalars().all()

        return [
            fact.fact
            for fact in reversed(facts)
        ]

    return []


async def change_karma(
    telegram_id: int,
    amount: int,
):
    async for session in get_session():

        result = await session.execute(
            select(UserProfile).where(
                UserProfile.telegram_id == telegram_id
            )
        )

        profile = result.scalar_one_or_none()

        if profile is None:

            profile = UserProfile(
                telegram_id=telegram_id,
                karma=amount,
            )

            session.add(profile)

        else:

            profile.karma += amount
            profile.updated_at = datetime.utcnow()

        await session.commit()

        return profile.karma

    return None


async def get_global_rating(
    limit: int = 10,
):
    async for session in get_session():

        result = await session.execute(
            select(UserProfile)
            .order_by(
                desc(UserProfile.karma)
            )
            .limit(limit)
        )

        return result.scalars().all()

    return []
