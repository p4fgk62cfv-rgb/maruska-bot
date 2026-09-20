from datetime import datetime, timedelta

from sqlalchemy import (
    select,
    desc,
    func,
    update,
)

from database.database import get_session

from database.models import (
    User,
    UserProfile,
    UserFact,
    MessageMemory,
    GroupMember,
    RatingVote,
    ActionImage,
)


RATING_COOLDOWN_HOURS = 24


# =========================================================
# GENDER HELPERS
# =========================================================

FEMALE_NAMES = {
    "анна", "мария", "елена", "ольга", "наталья", "наталия",
    "александра", "екатерина", "ирина", "светлана", "татьяна",
    "юлия", "юлиана", "виктория", "валерия", "дарья", "дария",
    "полина", "кристина", "диана", "алина", "арина", "карина",
    "марина", "лариса", "людмила", "оксана", "надежда", "любовь",
    "вероника", "евгения", "жанна", "зоя", "лидия", "инна",
    "нина", "раиса", "тамара", "вера", "галина", "алла", "лилия",
}

MALE_NAMES = {
    "стас", "станислав", "иван", "андрей", "александр", "сергей",
    "дмитрий", "максим", "михаил", "николай", "евгений", "роман",
    "артем", "артём", "алексей", "владимир", "виктор", "павел",
    "денис", "антон", "илья", "никита", "лука", "федор", "фёдор",
    "олег", "игорь", "василий", "юрий", "богдан", "ярослав",
    "матвей", "тимур", "глеб", "лев", "марк", "петр", "пётр",
    "саша", "женя", "валера", "миша", "дима", "серёжа", "сережа",
    "лёша", "леша", "паша", "вова",
}


def infer_gender(name: str | None) -> str:
    if not name:
        return "unknown"

    value = name.strip().lower()
    if not value:
        return "unknown"

    if value in FEMALE_NAMES:
        return "female"

    if value in MALE_NAMES:
        return "male"

    # Осторожные эвристики только для очевидных русских имён.
    if value.endswith(("а", "я")):
        return "female"

    if value.endswith(("й", "н", "р", "л", "м", "т", "д", "к", "с", "в", "г", "б", "п", "ф", "х", "ц", "ч", "ш", "щ")):
        return "male"

    return "unknown"


# =========================================================
# USERS
# =========================================================

async def save_user(
    telegram_id: int,
    username: str | None,
    first_name: str | None,
):
    gender = infer_gender(first_name or username)

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
                gender=gender,
            )
            session.add(user)
        else:
            user.username = username
            user.first_name = first_name
            if gender != "unknown":
                user.gender = gender

        await session.commit()



async def get_user_by_username(
    username: str,
):
    username = username.lstrip("@").lower()

    async for session in get_session():

        result = await session.execute(
            select(User).where(
                func.lower(User.username) == username
            )
        )

        return result.scalar_one_or_none()

    return None


async def get_user_by_telegram_id(
    telegram_id: int,
):
    async for session in get_session():
        result = await session.execute(
            select(User).where(
                User.telegram_id == telegram_id
            )
        )
        return result.scalar_one_or_none()

    return None


# =========================================================
# MESSAGES
# =========================================================

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

        # Global profile
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

        # Group member
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
            f"{item.username or 'Пользователь'}: {item.message}"
            for item in messages
        ]

    return []


# =========================================================
# PROFILES
# =========================================================

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
    display_name: str,
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


# =========================================================
# RATING
# =========================================================

async def can_vote_rating(
    giver_telegram_id: int,
    target_telegram_id: int,
):

    async for session in get_session():

        cooldown_time = (
            datetime.utcnow()
            - timedelta(hours=RATING_COOLDOWN_HOURS)
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


async def get_rating_stats(
    telegram_id: int,
):

    async for session in get_session():

        positive_result = await session.execute(
            select(
                func.count(RatingVote.id)
            ).where(
                RatingVote.target_telegram_id
                == telegram_id,

                RatingVote.amount > 0,
            )
        )

        positive = positive_result.scalar() or 0

        negative_result = await session.execute(
            select(
                func.count(RatingVote.id)
            ).where(
                RatingVote.target_telegram_id
                == telegram_id,

                RatingVote.amount < 0,
            )
        )

        negative = negative_result.scalar() or 0

        week_ago = (
            datetime.utcnow()
            - timedelta(days=7)
        )

        week_positive_result = await session.execute(
            select(
                func.count(RatingVote.id)
            ).where(
                RatingVote.target_telegram_id
                == telegram_id,

                RatingVote.amount > 0,

                RatingVote.created_at >= week_ago,
            )
        )

        week_positive = (
            week_positive_result.scalar() or 0
        )

        week_negative_result = await session.execute(
            select(
                func.count(RatingVote.id)
            ).where(
                RatingVote.target_telegram_id
                == telegram_id,

                RatingVote.amount < 0,

                RatingVote.created_at >= week_ago,
            )
        )

        week_negative = (
            week_negative_result.scalar() or 0
        )

        return {
            "positive": positive,
            "negative": negative,
            "week_positive": week_positive,
            "week_negative": week_negative,
        }

    return {
        "positive": 0,
        "negative": 0,
        "week_positive": 0,
        "week_negative": 0,
    }


# =========================================================
# FACTS
# =========================================================

async def add_fact(
    telegram_id: int,
    fact: str,
):

    async for session in get_session():

        item = UserFact(
            telegram_id=telegram_id,
            fact=fact,
        )

        session.add(item)

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

        return [
            item.fact
            for item in result.scalars().all()
        ]

    return []


# =========================================================
# ACTION IMAGES
# =========================================================

async def get_unused_action_image(
    action: str,
):

    async for session in get_session():

        result = await session.execute(
            select(ActionImage)
            .where(
                ActionImage.action == action,
                ActionImage.used == False,
            )
            .order_by(
                func.random()
            )
            .limit(1)
        )

        image = result.scalar_one_or_none()

        if image is None:
            return None

        image.used = True
        image.used_at = datetime.utcnow()

        await session.commit()

        return image

    return None


async def get_last_action_page(
    action: str,
):

    async for session in get_session():

        result = await session.execute(
            select(
                func.max(ActionImage.source_page)
            ).where(
                ActionImage.action == action
            )
        )

        page = result.scalar()

        return page or 0

    return 0


async def add_action_image(
    action: str,
    photo_id: str,
    image_url: str,
    photographer_name: str,
    photographer_url: str,
    unsplash_url: str,
    source_page: int,
):

    async for session in get_session():

        existing_result = await session.execute(
            select(ActionImage).where(
                ActionImage.action == action,
                ActionImage.photo_id == photo_id,
            )
        )

        existing = existing_result.scalar_one_or_none()

        if existing is not None:
            return False

        image = ActionImage(
            action=action,
            photo_id=photo_id,
            image_url=image_url,
            photographer_name=photographer_name,
            photographer_url=photographer_url,
            unsplash_url=unsplash_url,
            source_page=source_page,
            used=False,
        )

        session.add(image)

        await session.commit()

        return True

    return False


async def reset_action_images(
    action: str,
):

    async for session in get_session():

        await session.execute(
            update(ActionImage)
            .where(
                ActionImage.action == action
            )
            .values(
                used=False,
                used_at=None,
            )
        )

        await session.commit()

        return


async def release_action_image(
    image_id: int,
):

    async for session in get_session():

        result = await session.execute(
            select(ActionImage).where(
                ActionImage.id == image_id
            )
        )

        image = result.scalar_one_or_none()

        if image is not None:

            image.used = False
            image.used_at = None

            await session.commit()
