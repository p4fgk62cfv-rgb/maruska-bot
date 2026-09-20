from datetime import datetime, timedelta

from sqlalchemy import select, desc, func

from database.database import get_session
from database.models import (
    User,
    UserProfile,
    UserFact,
    MessageMemory,
    GroupMember,
    RatingVote,
)


RATING_COOLDOWN_HOURS = 24


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


async def can_vote_rating(
    giver_telegram_id: int,
    target_telegram_id: int,
):
    """
    Проверяет, может ли пользователь снова
    поставить рейтинг этому человеку.

    Один голос одному человеку раз в 24 часа.
    """

    async for session in get_session():

        cooldown_time = (
            datetime.utcnow()
            - timedelta(
                hours=RATING_COOLDOWN_HOURS
            )
        )

        result = await session.execute(
            select(RatingVote)
            .where(
                RatingVote.giver_telegram_id
                == giver_telegram_id,
                RatingVote.target_telegram_id
                == target_telegram_id,
                RatingVote.created_at
                >= cooldown_time,
            )
            .order_by(
                RatingVote.created_at.desc()
            )
            .limit(1)
        )

        vote = result.scalar_one_or_none()

        return vote is None

    return False


async def get_last_rating_vote(
    giver_telegram_id: int,
    target_telegram_id: int,
):
    async for session in get_session():

        result = await session.execute(
            select(RatingVote)
            .where(
                RatingVote.giver_telegram_id
                == giver_telegram_id,
                RatingVote.target_telegram_id
                == target_telegram_id,
            )
            .order_by(
                RatingVote.created_at.desc()
            )
            .limit(1)
        )

        return result.scalar_one_or_none()

    return None


async def add_rating_vote(
    giver_telegram_id: int,
    target_telegram_id: int,
    amount: int,
):
    """
    Добавляет голос и изменяет глобальный рейтинг.
    """

    async for session in get_session():

        profile_result = await session.execute(
            select(UserProfile).where(
                UserProfile.telegram_id
                == target_telegram_id
            )
        )

        profile = profile_result.scalar_one_or_none()

        if profile is None:

            profile = UserProfile(
                telegram_id=target_telegram_id,
                karma=max(amount, 0),
            )

            session.add(profile)

        else:

            profile.karma += amount

            # Рейтинг не уходит ниже нуля.
            if profile.karma < 0:
                profile.karma = 0

            profile.updated_at = datetime.utcnow()

        vote = RatingVote(
            giver_telegram_id=giver_telegram_id,
            target_telegram_id=target_telegram_id,
            amount=amount,
        )

        session.add(vote)

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
                desc(UserProfile.karma),
                UserProfile.display_name.asc(),
            )
            .limit(limit)
        )

        return result.scalars().all()

    return []


async def get_rating_position(
    telegram_id: int,
):
    """
    Место пользователя в глобальном рейтинге.
    """

    async for session in get_session():

        profile_result = await session.execute(
            select(UserProfile).where(
                UserProfile.telegram_id == telegram_id
            )
        )

        profile = profile_result.scalar_one_or_none()

        if profile is None:
            return None

        result = await session.execute(
            select(
                func.count(UserProfile.id)
            ).where(
                UserProfile.karma > profile.karma
            )
        )

        higher_count = result.scalar() or 0

        return higher_count + 1

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
