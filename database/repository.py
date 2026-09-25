from datetime import datetime, timedelta

from sqlalchemy import (
    select,
    desc,
    func,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert

from database.database import session_scope, utcnow

from database.models import (
    LibraryCollection,
    LibraryImage,
    LibraryLink,
    PunishRule,
    AutoReply,
    ShopOverride,
    ActionCustom,
    ActionToggle,
    ActionUsage,
    AdminRole,
    AuditEvent,
    Broadcast,
    HourlyStat,
    ChatWarning,
    BlockedUser,
    DailyStat,
    DrawingLike,
    GameRound,
    InventoryItem,
    UserAchievement,
    GroupSettings,
    Transaction,
    User,
    UserProfile,
    UserFact,
    MessageMemory,
    GroupMember,
    RatingVote,
    ActionImage,
)


RATING_COOLDOWN_HOURS = 24


def _week_key(moment=None) -> str:
    """
    Ключ недели вида 2026-W38. Меняется в понедельник.
    """
    value = moment or utcnow()
    year, week, _day = value.isocalendar()
    return f"{year}-W{week:02d}"


# =========================================================
# GENDER HELPERS
# =========================================================

FEMALE_NAMES = {
    "анна", "аня", "мария", "маша", "елена", "лена", "ольга", "оля",
    "наталья", "наталия", "наташа", "александра", "екатерина", "катя",
    "ирина", "ира", "светлана", "света", "татьяна", "таня",
    "юлия", "юля", "юлиана", "виктория", "вика", "валерия", "лера",
    "дарья", "дария", "даша", "полина", "кристина", "диана", "алина",
    "арина", "карина", "марина", "лариса", "людмила", "люда", "люся",
    "оксана", "надежда", "надя", "любовь", "люба", "вероника", "ника",
    "евгения", "жанна", "зоя", "лидия", "инна", "нина", "раиса",
    "тамара", "вера", "галина", "галя", "алла", "лилия", "лиля",
    "софия", "софья", "соня", "элина", "эльвира", "ульяна", "яна",
    "маруся", "маруська", "анастасия", "настя", "ксения", "ксюша",
}

MALE_NAMES = {
    "стас", "станислав", "иван", "ваня", "андрей", "александр", "сергей",
    "дмитрий", "максим", "михаил", "николай", "евгений", "роман",
    "артем", "артём", "алексей", "владимир", "виктор", "павел",
    "денис", "антон", "илья", "никита", "лука", "федор", "фёдор",
    "олег", "игорь", "василий", "юрий", "богдан", "ярослав",
    "матвей", "тимур", "глеб", "лев", "марк", "петр", "пётр",
    "саша", "женя", "валера", "миша", "дима", "серёжа", "сережа",
    "лёша", "леша", "паша", "вова", "костя", "константин", "кирилл",
    "даниил", "данил", "даня", "егор", "тарас", "остап", "назар",
}


LATIN_FEMALE_NAMES = {
    "anna", "anya", "ania", "maria", "masha", "elena", "lena", "olga",
    "olya", "natalia", "natalya", "natasha", "alexandra", "ekaterina",
    "katya", "kate", "irina", "ira", "svetlana", "sveta", "tatiana",
    "tatyana", "tanya", "julia", "yulia", "yuliya", "yulya", "victoria",
    "vika", "valeria", "lera", "daria", "dasha", "polina", "kristina",
    "diana", "alina", "arina", "karina", "marina", "lyudmila", "luda",
    "lyuda", "oksana", "nadya", "lyuba", "veronika", "nika", "zhanna",
    "nina", "vera", "galina", "alla", "lilia", "sofia", "sofya", "sonya",
    "ulyana", "yana", "anastasia", "nastya", "ksenia", "ksyusha",
    "marusya", "maruska",
}

LATIN_MALE_NAMES = {
    "stanislav", "stas", "ivan", "vanya", "andrey", "andrei", "alexander",
    "aleksandr", "sasha", "sergey", "sergei", "dmitry", "dmitriy", "dima",
    "maxim", "mikhail", "misha", "nikolay", "evgeny", "zhenya", "roman",
    "artem", "artyom", "alexey", "aleksey", "lesha", "vladimir", "vova",
    "viktor", "pavel", "pasha", "denis", "anton", "ilya", "nikita",
    "fedor", "oleg", "igor", "vasily", "yuri", "yury", "bogdan",
    "yaroslav", "matvey", "timur", "gleb", "lev", "mark", "petr", "peter",
    "kostya", "konstantin", "kirill", "daniil", "danil", "danya", "egor",
    "taras", "ostap", "nazar",
}

_FEMALE_LOOKUP = {name.replace("ё", "е") for name in FEMALE_NAMES}
_MALE_LOOKUP = {name.replace("ё", "е") for name in MALE_NAMES}

# Латиница -> кириллица, чтобы "STANISLAV" и "Nastya"
# тоже определялись по спискам имён.
_TRANSLIT = (
    ("shch", "щ"), ("sch", "щ"), ("zh", "ж"), ("kh", "х"), ("ts", "ц"),
    ("ch", "ч"), ("sh", "ш"), ("yu", "ю"), ("ya", "я"), ("ye", "е"),
    ("yo", "е"), ("iy", "ий"), ("ey", "ей"), ("j", "й"), ("y", "ы"),
    ("a", "а"), ("b", "б"), ("v", "в"), ("g", "г"), ("d", "д"),
    ("e", "е"), ("z", "з"), ("i", "и"), ("k", "к"), ("l", "л"),
    ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"), ("r", "р"),
    ("s", "с"), ("t", "т"), ("u", "у"), ("f", "ф"), ("h", "х"),
    ("c", "к"), ("w", "в"), ("x", "кс"), ("q", "к"),
)


def transliterate(value: str) -> str:
    result = value
    for latin, cyrillic in _TRANSLIT:
        result = result.replace(latin, cyrillic)
    # "мариа" -> "мария", но "диана" не трогаем
    if result.endswith("иа"):
        result = result[:-2] + "ия"
    return result


def infer_gender(name: str | None) -> str:
    if not name:
        return "unknown"

    value = name.strip().lower().replace("ё", "е")
    if not value:
        return "unknown"

    # Имя может быть "Анна 🌸" или "Anna | Prague"
    first_token = value.split()[0].strip(".,!?|-–—_")

    if first_token and first_token.isascii():
        if first_token in LATIN_FEMALE_NAMES:
            return "female"
        if first_token in LATIN_MALE_NAMES:
            return "male"

    candidates = [value, first_token]

    if first_token and first_token.isascii():
        candidates.append(transliterate(first_token))

    for candidate in candidates:
        if candidate in _FEMALE_LOOKUP:
            return "female"
        if candidate in _MALE_LOOKUP:
            return "male"

    # Осторожные эвристики только для кириллицы.
    if not any("а" <= char <= "я" for char in first_token):
        return "unknown"

    if first_token.endswith(("а", "я")):
        return "female"

    if first_token.endswith((
        "й", "н", "р", "л", "м", "т", "д", "к", "с",
        "в", "г", "б", "п", "ф", "х", "ц", "ч", "ш", "щ",
    )):
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

    async with session_scope() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
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


async def get_user_by_username(username: str) -> User | None:
    normalized = username.lstrip("@").lower()

    async with session_scope() as session:
        result = await session.execute(
            select(User).where(
                func.lower(User.username) == normalized
            )
        )
        return result.scalar_one_or_none()


async def get_user_by_telegram_id(telegram_id: int) -> User | None:
    async with session_scope() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


# =========================================================
# MESSAGES
# =========================================================

async def save_message(
    chat_id: int,
    telegram_user_id: int,
    username: str | None,
    message: str,
    store_text: bool = True,
):
    """
    Счётчики сообщений обновляются всегда. Текст сохраняется, только
    если его можно помнить: память Мары выключена или человек в
    исключениях — текста в базе не будет, а статистика останется.
    """
    async with session_scope() as session:

        if store_text:
            session.add(
                MessageMemory(
                    chat_id=chat_id,
                    telegram_user_id=telegram_user_id,
                    username=username,
                    message=message,
                )
            )

        # Глобальный профиль
        profile_result = await session.execute(
            select(UserProfile).where(
                UserProfile.telegram_id == telegram_user_id
            )
        )

        profile = profile_result.scalar_one_or_none()

        if profile is None:
            session.add(
                UserProfile(
                    telegram_id=telegram_user_id,
                    display_name=username,
                    messages_count=1,
                )
            )
        else:
            if username:
                profile.display_name = username
            profile.messages_count += 1
            profile.updated_at = utcnow()

        # Участник конкретной группы
        member_result = await session.execute(
            select(GroupMember).where(
                GroupMember.chat_id == chat_id,
                GroupMember.telegram_id == telegram_user_id,
            )
        )

        member = member_result.scalar_one_or_none()

        if member is None:
            session.add(
                GroupMember(
                    chat_id=chat_id,
                    telegram_id=telegram_user_id,
                    display_name=username,
                    messages_count=1,
                    week_messages=1,
                    week_start=_week_key(),
                )
            )
        else:
            if username:
                member.display_name = username
            member.messages_count += 1
            member.updated_at = utcnow()

            week = _week_key()

            if member.week_start != week:
                member.week_start = week
                member.week_messages = 0

            member.week_messages += 1

        await session.commit()


async def get_recent_messages(chat_id: int, limit: int = 8) -> list[str]:
    async with session_scope() as session:
        result = await session.execute(
            select(MessageMemory)
            .where(MessageMemory.chat_id == chat_id)
            .order_by(MessageMemory.created_at.desc())
            .limit(limit)
        )

        messages = list(result.scalars().all())
        messages.reverse()

        return [
            f"{item.username or 'Пользователь'}: {item.message}"
            for item in messages
        ]


async def cleanup_old_messages(chat_id: int, keep: int = 200):
    """
    Чтобы message_memory не разрасталась бесконечно.
    """
    async with session_scope() as session:
        subquery = (
            select(MessageMemory.id)
            .where(MessageMemory.chat_id == chat_id)
            .order_by(MessageMemory.created_at.desc())
            .limit(keep)
            .scalar_subquery()
        )

        await session.execute(
            MessageMemory.__table__.delete().where(
                MessageMemory.chat_id == chat_id,
                MessageMemory.id.not_in(subquery),
            )
        )

        await session.commit()


# =========================================================
# PROFILES
# =========================================================

async def get_profile(telegram_id: int) -> UserProfile | None:
    async with session_scope() as session:
        result = await session.execute(
            select(UserProfile).where(
                UserProfile.telegram_id == telegram_id
            )
        )
        return result.scalar_one_or_none()


async def create_profile_if_needed(
    telegram_id: int,
    display_name: str,
) -> UserProfile | None:
    async with session_scope() as session:
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


# =========================================================
# RATING
# =========================================================

async def can_vote_rating(
    giver_telegram_id: int,
    target_telegram_id: int,
    cooldown_hours: int | None = None,
) -> bool:
    hours = cooldown_hours or RATING_COOLDOWN_HOURS

    async with session_scope() as session:
        cooldown_time = utcnow() - timedelta(hours=hours)

        result = await session.execute(
            select(RatingVote)
            .where(
                RatingVote.giver_telegram_id == giver_telegram_id,
                RatingVote.target_telegram_id == target_telegram_id,
                RatingVote.created_at >= cooldown_time,
            )
            .order_by(RatingVote.created_at.desc())
            .limit(1)
        )

        return result.scalar_one_or_none() is None


async def get_last_rating_vote(
    giver_telegram_id: int,
    target_telegram_id: int,
) -> RatingVote | None:
    async with session_scope() as session:
        result = await session.execute(
            select(RatingVote)
            .where(
                RatingVote.giver_telegram_id == giver_telegram_id,
                RatingVote.target_telegram_id == target_telegram_id,
            )
            .order_by(RatingVote.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def add_rating_vote(
    giver_telegram_id: int,
    target_telegram_id: int,
    amount: int,
    display_name: str | None = None,
) -> int:
    async with session_scope() as session:
        profile_result = await session.execute(
            select(UserProfile).where(
                UserProfile.telegram_id == target_telegram_id
            )
        )

        profile = profile_result.scalar_one_or_none()

        if profile is None:
            profile = UserProfile(
                telegram_id=target_telegram_id,
                display_name=display_name,
                karma=max(amount, 0),
            )
            session.add(profile)
        else:
            profile.karma += amount
            if profile.karma < 0:
                profile.karma = 0
            if display_name:
                profile.display_name = display_name
            profile.updated_at = utcnow()

        session.add(
            RatingVote(
                giver_telegram_id=giver_telegram_id,
                target_telegram_id=target_telegram_id,
                amount=amount,
            )
        )

        await session.commit()

        return profile.karma


async def get_global_rating(limit: int = 10):
    async with session_scope() as session:
        result = await session.execute(
            select(UserProfile)
            .order_by(
                desc(UserProfile.karma),
                UserProfile.display_name.asc(),
            )
            .limit(limit)
        )
        return list(result.scalars().all())


async def get_rating_position(telegram_id: int) -> int | None:
    async with session_scope() as session:
        profile_result = await session.execute(
            select(UserProfile).where(
                UserProfile.telegram_id == telegram_id
            )
        )

        profile = profile_result.scalar_one_or_none()

        if profile is None:
            return None

        result = await session.execute(
            select(func.count(UserProfile.id)).where(
                UserProfile.karma > profile.karma
            )
        )

        return (result.scalar() or 0) + 1


async def get_rating_stats(telegram_id: int) -> dict:
    async with session_scope() as session:
        week_ago = utcnow() - timedelta(days=7)

        result = await session.execute(
            select(
                func.count(RatingVote.id).filter(RatingVote.amount > 0),
                func.count(RatingVote.id).filter(RatingVote.amount < 0),
                func.count(RatingVote.id).filter(
                    RatingVote.amount > 0,
                    RatingVote.created_at >= week_ago,
                ),
                func.count(RatingVote.id).filter(
                    RatingVote.amount < 0,
                    RatingVote.created_at >= week_ago,
                ),
            ).where(RatingVote.target_telegram_id == telegram_id)
        )

        positive, negative, week_positive, week_negative = result.one()

        return {
            "positive": positive or 0,
            "negative": negative or 0,
            "week_positive": week_positive or 0,
            "week_negative": week_negative or 0,
        }


# =========================================================
# FACTS
# =========================================================

async def add_fact(telegram_id: int, fact: str):
    async with session_scope() as session:
        session.add(UserFact(telegram_id=telegram_id, fact=fact))
        await session.commit()


async def get_facts(telegram_id: int, limit: int = 20) -> list[str]:
    async with session_scope() as session:
        result = await session.execute(
            select(UserFact)
            .where(UserFact.telegram_id == telegram_id)
            .order_by(UserFact.created_at.desc())
            .limit(limit)
        )
        return [item.fact for item in result.scalars().all()]


# =========================================================
# ACTION IMAGES
# =========================================================

async def get_cached_action_image(action: str) -> ActionImage | None:
    """
    Неиспользованная картинка с готовым telegram_file_id.

    Только такие и годятся для повторной отправки: ссылки источника
    протухают через сутки, а file_id живёт вечно.
    """
    async with session_scope() as session:
        result = await session.execute(
            select(ActionImage)
            .where(
                ActionImage.action == action,
                ActionImage.used.is_(False),
                ActionImage.telegram_file_id.is_not(None),
            )
            .order_by(func.random())
            .limit(1)
            .with_for_update(skip_locked=True)
        )

        image = result.scalar_one_or_none()

        if image is None:
            return None

        image.used = True
        image.used_at = utcnow()

        await session.commit()

        return image


async def count_cached_images(action: str) -> int:
    async with session_scope() as session:
        result = await session.execute(
            select(func.count(ActionImage.id)).where(
                ActionImage.action == action,
                ActionImage.telegram_file_id.is_not(None),
            )
        )
        return result.scalar() or 0


async def reset_cached_images(action: str):
    """
    Возвращает в оборот только те картинки, что уже в Telegram.
    """
    async with session_scope() as session:
        await session.execute(
            update(ActionImage)
            .where(
                ActionImage.action == action,
                ActionImage.telegram_file_id.is_not(None),
            )
            .values(used=False, used_at=None)
        )
        await session.commit()


async def known_photo_ids(action: str, limit: int = 300) -> set[str]:
    """
    Что уже есть в коллекции — чтобы не качать одно и то же дважды.
    """
    async with session_scope() as session:
        result = await session.execute(
            select(ActionImage.photo_id)
            .where(ActionImage.action == action)
            .limit(limit)
        )
        return set(result.scalars().all())


async def save_sent_image(
    action: str,
    provider: str,
    photo_id: str,
    file_id: str,
) -> None:
    """
    Запоминает отправленную картинку по file_id. Ссылка источника
    не сохраняется: она всё равно протухнет.
    """
    async with session_scope() as session:
        existing = await session.execute(
            select(ActionImage).where(
                ActionImage.action == action,
                ActionImage.photo_id == photo_id,
            )
        )

        item = existing.scalar_one_or_none()

        if item is None:
            session.add(
                ActionImage(
                    action=action,
                    provider=provider,
                    photo_id=photo_id,
                    image_url="",
                    telegram_file_id=file_id,
                    source_page=0,
                    used=True,
                    used_at=utcnow(),
                )
            )
        else:
            item.telegram_file_id = file_id
            item.used = True
            item.used_at = utcnow()

        await session.commit()


async def get_unused_action_image(action: str) -> ActionImage | None:
    async with session_scope() as session:
        result = await session.execute(
            select(ActionImage)
            .where(
                ActionImage.action == action,
                ActionImage.used.is_(False),
            )
            .order_by(func.random())
            .limit(1)
            .with_for_update(skip_locked=True)
        )

        image = result.scalar_one_or_none()

        if image is None:
            return None

        image.used = True
        image.used_at = utcnow()

        await session.commit()

        return image


async def get_last_action_page(action: str) -> int:
    async with session_scope() as session:
        result = await session.execute(
            select(func.max(ActionImage.source_page)).where(
                ActionImage.action == action
            )
        )
        return result.scalar() or 0


async def count_action_images(action: str) -> int:
    async with session_scope() as session:
        result = await session.execute(
            select(func.count(ActionImage.id)).where(
                ActionImage.action == action
            )
        )
        return result.scalar() or 0


async def add_action_image(
    action: str,
    photo_id: str,
    image_url: str,
    source_page: int,
    provider: str = "pixabay",
    fallback_url: str | None = None,
    photographer_name: str | None = None,
    photographer_url: str | None = None,
    source_url: str | None = None,
) -> bool:
    async with session_scope() as session:
        existing_result = await session.execute(
            select(ActionImage.id).where(
                ActionImage.action == action,
                ActionImage.photo_id == photo_id,
            )
        )

        if existing_result.scalar_one_or_none() is not None:
            return False

        session.add(
            ActionImage(
                action=action,
                provider=provider,
                photo_id=photo_id,
                image_url=image_url,
                fallback_url=fallback_url,
                photographer_name=photographer_name,
                photographer_url=photographer_url,
                unsplash_url=source_url,
                source_page=source_page,
                used=False,
            )
        )

        await session.commit()

        return True


async def reset_action_images(action: str):
    async with session_scope() as session:
        await session.execute(
            update(ActionImage)
            .where(ActionImage.action == action)
            .values(used=False, used_at=None)
        )
        await session.commit()


async def release_action_image(image_id: int):
    async with session_scope() as session:
        await session.execute(
            update(ActionImage)
            .where(ActionImage.id == image_id)
            .values(used=False, used_at=None)
        )
        await session.commit()


async def set_action_image_file_id(image_id: int, file_id: str):
    async with session_scope() as session:
        await session.execute(
            update(ActionImage)
            .where(ActionImage.id == image_id)
            .values(telegram_file_id=file_id)
        )
        await session.commit()


async def drop_action_image(image_id: int):
    """
    Битая ссылка — выкидываем из коллекции совсем.
    """
    async with session_scope() as session:
        await session.execute(
            ActionImage.__table__.delete().where(
                ActionImage.id == image_id
            )
        )
        await session.commit()


# =========================================================
# ИГРЫ
# =========================================================

async def get_active_round(chat_id: int, game: str = "crocodile"):
    async with session_scope() as session:
        result = await session.execute(
            select(GameRound)
            .where(
                GameRound.chat_id == chat_id,
                GameRound.game == game,
                GameRound.status.in_(("waiting", "playing")),
            )
            .order_by(GameRound.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def load_active_rounds(game: str = "crocodile"):
    """
    После перезапуска подтягиваем незавершённые раунды в память.
    """
    async with session_scope() as session:
        result = await session.execute(
            select(GameRound).where(
                GameRound.game == game,
                GameRound.status.in_(("waiting", "playing")),
            )
        )
        return list(result.scalars().all())


async def get_round_by_token(token: str):
    if not token:
        return None

    async with session_scope() as session:
        result = await session.execute(
            select(GameRound)
            .where(GameRound.token == token)
            .order_by(GameRound.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def create_round(
    chat_id: int,
    host_telegram_id: int,
    host_name: str | None,
    word: str,
    level: str,
    token: str | None = None,
    game: str = "crocodile",
) -> GameRound:
    async with session_scope() as session:
        # Старые незакрытые раунды в этом чате закрываем
        await session.execute(
            update(GameRound)
            .where(
                GameRound.chat_id == chat_id,
                GameRound.game == game,
                GameRound.status.in_(("waiting", "playing")),
            )
            .values(status="cancelled", finished_at=utcnow())
        )

        item = GameRound(
            chat_id=chat_id,
            game=game,
            host_telegram_id=host_telegram_id,
            host_name=host_name,
            word=word,
            level=level,
            token=token,
            status="waiting",
        )

        session.add(item)
        await session.commit()

        return item


async def update_round(round_id: int, **values):
    async with session_scope() as session:
        await session.execute(
            update(GameRound)
            .where(GameRound.id == round_id)
            .values(**values)
        )
        await session.commit()


async def finish_round(
    round_id: int,
    winner_telegram_id: int | None,
    winner_name: str | None,
    status: str = "finished",
):
    await update_round(
        round_id,
        status=status,
        winner_telegram_id=winner_telegram_id,
        winner_name=winner_name,
        finished_at=utcnow(),
    )


async def get_round(round_id: int):
    async with session_scope() as session:
        result = await session.execute(
            select(GameRound).where(GameRound.id == round_id)
        )
        return result.scalar_one_or_none()


async def add_drawing_like(round_id: int, telegram_id: int) -> tuple[bool, int]:
    """
    Ставит лайк рисунку. Возвращает (засчитан ли, сколько всего).
    Повторный лайк от того же человека не засчитывается.
    """
    async with session_scope() as session:
        existing = await session.execute(
            select(DrawingLike.id).where(
                DrawingLike.round_id == round_id,
                DrawingLike.telegram_id == telegram_id,
            )
        )

        item = await session.get(GameRound, round_id)

        if item is None:
            return False, 0

        if existing.scalar_one_or_none() is not None:
            return False, item.likes

        session.add(
            DrawingLike(round_id=round_id, telegram_id=telegram_id)
        )

        item.likes += 1

        await session.commit()

        return True, item.likes


async def get_last_winner(chat_id: int, game: str = "crocodile"):
    async with session_scope() as session:
        result = await session.execute(
            select(GameRound)
            .where(
                GameRound.chat_id == chat_id,
                GameRound.game == game,
                GameRound.status == "finished",
                GameRound.winner_telegram_id.is_not(None),
            )
            .order_by(GameRound.finished_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def add_karma(
    telegram_id: int,
    amount: int,
    display_name: str | None = None,
) -> int:
    """
    Прямое начисление рейтинга (без кулдауна и без записи голоса).
    Используется играми.
    """
    async with session_scope() as session:
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
                karma=max(amount, 0),
            )
            session.add(profile)
        else:
            profile.karma = max(profile.karma + amount, 0)
            if display_name:
                profile.display_name = display_name
            profile.updated_at = utcnow()

        await session.commit()

        return profile.karma


async def bump_game_stats(
    telegram_id: int,
    played: int = 0,
    won: int = 0,
    display_name: str | None = None,
):
    async with session_scope() as session:
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
                games_played=max(played, 0),
                games_won=max(won, 0),
            )
            session.add(profile)
        else:
            profile.games_played += played
            profile.games_won += won
            if display_name:
                profile.display_name = display_name
            profile.updated_at = utcnow()

        await session.commit()


# =========================================================
# НАСТРОЙКИ ГРУПП
# =========================================================

async def get_group_settings(chat_id: int) -> dict:
    async with session_scope() as session:
        result = await session.execute(
            select(GroupSettings).where(
                GroupSettings.chat_id == chat_id
            )
        )

        item = result.scalar_one_or_none()

        return dict(item.values or {}) if item else {}


async def set_group_setting(
    chat_id: int,
    key: str,
    value,
    title: str | None = None,
) -> dict:
    async with session_scope() as session:
        result = await session.execute(
            select(GroupSettings).where(
                GroupSettings.chat_id == chat_id
            )
        )

        item = result.scalar_one_or_none()

        if item is None:
            item = GroupSettings(
                chat_id=chat_id,
                title=title,
                values={key: value},
            )
            session.add(item)
        else:
            # JSON-поле нужно переприсвоить целиком,
            # иначе SQLAlchemy не заметит изменения.
            merged = dict(item.values or {})
            merged[key] = value
            item.values = merged

            if title:
                item.title = title

            item.updated_at = utcnow()

        await session.commit()

        return dict(item.values or {})


# =========================================================
# ЭКОНОМИКА
# =========================================================

async def _profile_for_update(session, telegram_id: int, display_name=None):
    result = await session.execute(
        select(UserProfile)
        .where(UserProfile.telegram_id == telegram_id)
        .with_for_update()
    )

    profile = result.scalar_one_or_none()

    if profile is None:
        profile = UserProfile(
            telegram_id=telegram_id,
            display_name=display_name,
        )
        session.add(profile)
        await session.flush()

    return profile


async def get_balance(telegram_id: int) -> int:
    async with session_scope() as session:
        result = await session.execute(
            select(UserProfile.coins).where(
                UserProfile.telegram_id == telegram_id
            )
        )
        return result.scalar() or 0


async def change_balance(
    telegram_id: int,
    amount: int,
    reason: str,
    note: str | None = None,
    chat_id: int | None = None,
    display_name: str | None = None,
    allow_negative: bool = False,
) -> tuple[bool, int]:
    """
    Начисление или списание одной транзакцией.

    Возвращает (получилось, новый баланс). Списание не проходит,
    если денег не хватает и allow_negative=False.
    """
    async with session_scope() as session:
        profile = await _profile_for_update(session, telegram_id, display_name)

        new_balance = profile.coins + amount

        if new_balance < 0 and not allow_negative:
            return False, profile.coins

        profile.coins = max(new_balance, 0)

        if display_name:
            profile.display_name = display_name

        profile.updated_at = utcnow()

        session.add(
            Transaction(
                telegram_id=telegram_id,
                chat_id=chat_id,
                amount=amount,
                balance_after=profile.coins,
                reason=reason,
                note=note,
            )
        )

        await session.commit()

        return True, profile.coins


async def claim_daily_bonus(
    telegram_id: int,
    amount: int,
    chat_id: int | None = None,
    display_name: str | None = None,
) -> dict:
    """
    Забирает ежедневный бонус.

    Одна попытка в сутки по календарной дате UTC. Серия растёт
    только если прошлый бонус был ровно вчера; любой пропуск
    обнуляет её.
    """
    async with session_scope() as session:
        profile = await _profile_for_update(session, telegram_id, display_name)

        now = utcnow()
        last = profile.last_bonus_at

        if last is not None and last.date() == now.date():
            return {
                "claimed": False,
                "balance": profile.coins,
                "streak": profile.bonus_streak,
                "best_streak": profile.best_streak,
                "next_at": now.replace(
                    hour=0, minute=0, second=0, microsecond=0
                ) + timedelta(days=1),
            }

        gap = (now.date() - last.date()).days if last is not None else None

        if gap == 1:
            profile.bonus_streak += 1
        else:
            profile.bonus_streak = 1

        profile.best_streak = max(profile.best_streak, profile.bonus_streak)
        profile.last_bonus_at = now
        profile.coins += amount

        if display_name:
            profile.display_name = display_name

        profile.updated_at = utcnow()

        session.add(
            Transaction(
                telegram_id=telegram_id,
                chat_id=chat_id,
                amount=amount,
                balance_after=profile.coins,
                reason="bonus",
                note=f"Ежедневный бонус, серия {profile.bonus_streak}",
            )
        )

        await session.commit()

        return {
            "claimed": True,
            "amount": amount,
            "balance": profile.coins,
            "streak": profile.bonus_streak,
            "best_streak": profile.best_streak,
        }


async def get_transactions(telegram_id: int, limit: int = 10):
    async with session_scope() as session:
        result = await session.execute(
            select(Transaction)
            .where(Transaction.telegram_id == telegram_id)
            .order_by(Transaction.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


async def get_richest(limit: int = 10):
    async with session_scope() as session:
        result = await session.execute(
            select(UserProfile)
            .where(UserProfile.coins > 0)
            .order_by(desc(UserProfile.coins))
            .limit(limit)
        )
        return list(result.scalars().all())


# =========================================================
# ИНВЕНТАРЬ И ПОДАРКИ
# =========================================================

async def add_inventory_item(
    telegram_id: int,
    item_key: str,
    qty: int = 1,
    from_telegram_id: int | None = None,
    from_name: str | None = None,
):
    async with session_scope() as session:
        result = await session.execute(
            select(InventoryItem).where(
                InventoryItem.telegram_id == telegram_id,
                InventoryItem.item_key == item_key,
                InventoryItem.from_telegram_id.is_(None)
                if from_telegram_id is None
                else InventoryItem.from_telegram_id == from_telegram_id,
            )
        )

        item = result.scalar_one_or_none()

        if item is None:
            session.add(
                InventoryItem(
                    telegram_id=telegram_id,
                    item_key=item_key,
                    qty=qty,
                    from_telegram_id=from_telegram_id,
                    from_name=from_name,
                )
            )
        else:
            item.qty += qty
            if from_name:
                item.from_name = from_name

        await session.commit()


async def get_inventory(telegram_id: int):
    async with session_scope() as session:
        result = await session.execute(
            select(InventoryItem)
            .where(InventoryItem.telegram_id == telegram_id)
            .order_by(InventoryItem.created_at.desc())
        )
        return list(result.scalars().all())


async def count_inventory(telegram_id: int) -> int:
    async with session_scope() as session:
        result = await session.execute(
            select(func.coalesce(func.sum(InventoryItem.qty), 0)).where(
                InventoryItem.telegram_id == telegram_id
            )
        )
        return result.scalar() or 0


# =========================================================
# ОПЫТ, УРОВНИ, ДОСТИЖЕНИЯ
# =========================================================

async def award_xp(
    telegram_id: int,
    amount: int,
    display_name: str | None = None,
    daily_cap: int | None = None,
    per_message: int = 0,
) -> dict:
    """
    Начисляет опыт и пересчитывает уровень.

    daily_cap ограничивает только опыт за сообщения: награды за
    игры и бонусы дают опыт всегда, иначе активный день обнулял бы
    смысл побеждать.

    Возвращает {xp, level, level_up, gained}.
    """
    from progress.xp import level_from_xp

    async with session_scope() as session:
        profile = await _profile_for_update(session, telegram_id, display_name)

        today = utcnow().strftime("%Y-%m-%d")

        if profile.xp_day != today:
            profile.xp_day = today
            profile.xp_today = 0

        gain = amount

        if per_message and daily_cap is not None:
            room = max(daily_cap - profile.xp_today, 0)
            gain = min(amount, room)
            profile.xp_today += gain

        if gain <= 0:
            return {
                "xp": profile.xp,
                "level": profile.level,
                "level_up": False,
                "gained": 0,
            }

        old_level = profile.level or 1

        profile.xp += gain
        profile.level = level_from_xp(profile.xp)

        if display_name:
            profile.display_name = display_name

        profile.updated_at = utcnow()

        await session.commit()

        return {
            "xp": profile.xp,
            "level": profile.level,
            "level_up": profile.level > old_level,
            "gained": gain,
        }


async def bump_counter(telegram_id: int, field: str, amount: int = 1):
    """
    Увеличивает произвольный счётчик профиля: подарки, лайки, дни бонуса.
    """
    allowed = {"gifts_sent", "likes_received", "bonus_days"}

    if field not in allowed:
        return

    async with session_scope() as session:
        profile = await _profile_for_update(session, telegram_id)

        setattr(profile, field, (getattr(profile, field) or 0) + amount)
        profile.updated_at = utcnow()

        await session.commit()


async def get_unlocked_achievements(telegram_id: int) -> set[str]:
    async with session_scope() as session:
        result = await session.execute(
            select(UserAchievement.achievement_key).where(
                UserAchievement.telegram_id == telegram_id
            )
        )
        return set(result.scalars().all())


async def unlock_achievement(telegram_id: int, key: str) -> bool:
    """
    Отмечает достижение открытым. False — уже было открыто.
    """
    async with session_scope() as session:
        existing = await session.execute(
            select(UserAchievement.id).where(
                UserAchievement.telegram_id == telegram_id,
                UserAchievement.achievement_key == key,
            )
        )

        if existing.scalar_one_or_none() is not None:
            return False

        session.add(
            UserAchievement(
                telegram_id=telegram_id,
                achievement_key=key,
            )
        )

        await session.commit()

        return True


async def get_xp_top(limit: int = 10):
    async with session_scope() as session:
        result = await session.execute(
            select(UserProfile)
            .where(UserProfile.xp > 0)
            .order_by(desc(UserProfile.xp))
            .limit(limit)
        )
        return list(result.scalars().all())


async def collect_stats(telegram_id: int) -> dict:
    """
    Срез показателей для проверки достижений.
    """
    async with session_scope() as session:
        profile_result = await session.execute(
            select(UserProfile).where(
                UserProfile.telegram_id == telegram_id
            )
        )

        profile = profile_result.scalar_one_or_none()

        if profile is None:
            return {}

        items_result = await session.execute(
            select(func.coalesce(func.sum(InventoryItem.qty), 0)).where(
                InventoryItem.telegram_id == telegram_id
            )
        )

        return {
            "messages": profile.messages_count or 0,
            "level": profile.level or 1,
            "xp": profile.xp or 0,
            "coins": profile.coins or 0,
            "karma": profile.karma or 0,
            "games_won": profile.games_won or 0,
            "games_played": profile.games_played or 0,
            "best_streak": profile.best_streak or 0,
            "bonus_days": profile.bonus_days or 0,
            "gifts_sent": profile.gifts_sent or 0,
            "likes": profile.likes_received or 0,
            "items": items_result.scalar() or 0,
        }


# =========================================================
# НЕДЕЛЬНЫЕ ИТОГИ
# =========================================================

async def get_week_top(chat_id: int, limit: int = 5):
    """
    Самые активные за текущую неделю в этом чате.
    """
    week = _week_key()

    async with session_scope() as session:
        result = await session.execute(
            select(GroupMember)
            .where(
                GroupMember.chat_id == chat_id,
                GroupMember.week_start == week,
                GroupMember.week_messages > 0,
            )
            .order_by(desc(GroupMember.week_messages))
            .limit(limit)
        )
        return list(result.scalars().all())


async def get_week_earners(chat_id: int, limit: int = 3):
    """
    Кто больше всех заработал алмазов за неделю в этом чате.
    """
    since = utcnow() - timedelta(days=7)

    async with session_scope() as session:
        result = await session.execute(
            select(
                Transaction.telegram_id,
                func.sum(Transaction.amount).label("total"),
            )
            .where(
                Transaction.chat_id == chat_id,
                Transaction.amount > 0,
                Transaction.created_at >= since,
            )
            .group_by(Transaction.telegram_id)
            .order_by(desc("total"))
            .limit(limit)
        )

        rows = result.all()

        if not rows:
            return []

        ids = [row[0] for row in rows]

        names_result = await session.execute(
            select(UserProfile.telegram_id, UserProfile.display_name).where(
                UserProfile.telegram_id.in_(ids)
            )
        )

        names = dict(names_result.all())

        return [
            (names.get(user_id) or "Игрок", int(total or 0))
            for user_id, total in rows
        ]


async def get_week_winners(chat_id: int, limit: int = 3):
    """
    Кто чаще всех выигрывал в играх за неделю.
    """
    since = utcnow() - timedelta(days=7)

    async with session_scope() as session:
        result = await session.execute(
            select(
                GameRound.winner_name,
                func.count(GameRound.id).label("wins"),
            )
            .where(
                GameRound.chat_id == chat_id,
                GameRound.status == "finished",
                GameRound.winner_telegram_id.is_not(None),
                GameRound.finished_at >= since,
            )
            .group_by(GameRound.winner_name)
            .order_by(desc("wins"))
            .limit(limit)
        )

        return [
            (name or "Игрок", int(wins))
            for name, wins in result.all()
        ]


async def get_member(chat_id: int, telegram_id: int):
    async with session_scope() as session:
        result = await session.execute(
            select(GroupMember).where(
                GroupMember.chat_id == chat_id,
                GroupMember.telegram_id == telegram_id,
            )
        )
        return result.scalar_one_or_none()


async def get_active_chats(days: int = 14) -> list[int]:
    """
    Чаты, где за последние дни кто-то писал. Нужно рассылке итогов,
    чтобы не будить мёртвые группы.
    """
    since = utcnow() - timedelta(days=days)

    async with session_scope() as session:
        result = await session.execute(
            select(GroupMember.chat_id)
            .where(GroupMember.updated_at >= since)
            .group_by(GroupMember.chat_id)
        )
        return [chat_id for chat_id in result.scalars().all() if chat_id < 0]


# =========================================================
# СТАТИСТИКА ПО ДНЯМ (для веб-панели)
# =========================================================

def _day_key(moment=None) -> str:
    return (moment or utcnow()).strftime("%Y-%m-%d")


DAILY_FIELDS = (
    "messages", "actions", "games", "new_users", "active_users",
    "warnings", "mutes", "bans", "deleted", "ai_requests",
    "commands", "autoreplies", "images", "xp",
)


async def bump_daily_stat(chat_id: int, field: str = "messages", amount: int = 1):
    """
    Копит активность по дням. Вызывается из горячего пути,
    поэтому ошибки здесь не должны ломать обработку сообщения.
    """
    if field not in DAILY_FIELDS:
        return

    day = _day_key()

    async with session_scope() as session:
        result = await session.execute(
            select(DailyStat).where(
                DailyStat.chat_id == chat_id,
                DailyStat.day == day,
            )
        )

        item = result.scalar_one_or_none()

        if item is None:
            item = DailyStat(chat_id=chat_id, day=day)
            setattr(item, field, amount)
            session.add(item)
        else:
            setattr(item, field, (getattr(item, field) or 0) + amount)

        await session.commit()


async def backfill_daily_stats() -> int:
    """
    Восстанавливает историю графиков из message_memory.

    Таблица daily_stats появилась позже, чем бот начал работать,
    поэтому прошлые дни в ней пусты. А message_memory хранит все
    сообщения с датами — из неё и досчитываем.

    Заполняет только отсутствующие дни, так что запускать можно
    при каждом старте: повторно ничего не задвоится.
    """
    day_expr = func.to_char(MessageMemory.created_at, "YYYY-MM-DD")

    async with session_scope() as session:
        history = (
            await session.execute(
                select(
                    MessageMemory.chat_id,
                    day_expr,
                    func.count(MessageMemory.id),
                )
                .where(MessageMemory.chat_id < 0)
                .group_by(MessageMemory.chat_id, day_expr)
            )
        ).all()

        if not history:
            return 0

        existing = (
            await session.execute(
                select(DailyStat.chat_id, DailyStat.day)
            )
        ).all()

        known = {(chat_id, day) for chat_id, day in existing}

        added = 0

        for chat_id, day, count in history:
            if (chat_id, day) in known:
                continue

            session.add(
                DailyStat(
                    chat_id=chat_id,
                    day=day,
                    messages=int(count or 0),
                )
            )
            added += 1

        await session.commit()

        return added


async def get_daily_series(chat_id: int | None, days: int = 7) -> list[dict]:
    """
    Ряд по дням для графика. chat_id=None — по всем чатам сразу.
    """
    since = (utcnow() - timedelta(days=days - 1)).strftime("%Y-%m-%d")

    async with session_scope() as session:
        query = select(
            DailyStat.day,
            func.sum(DailyStat.messages),
            func.sum(DailyStat.actions),
            func.sum(DailyStat.games),
        ).where(DailyStat.day >= since)

        if chat_id is not None:
            query = query.where(DailyStat.chat_id == chat_id)

        result = await session.execute(
            query.group_by(DailyStat.day).order_by(DailyStat.day)
        )

        rows = {
            day: {
                "messages": int(messages or 0),
                "actions": int(actions or 0),
                "games": int(games or 0),
            }
            for day, messages, actions, games in result.all()
        }

    series = []
    start = utcnow() - timedelta(days=days - 1)

    for offset in range(days):
        day = (start + timedelta(days=offset)).strftime("%Y-%m-%d")
        values = rows.get(day, {"messages": 0, "actions": 0, "games": 0})
        series.append({"day": day, **values})

    return series


# =========================================================
# БЛОКИРОВКИ
# =========================================================

async def block_user(chat_id: int, telegram_id: int, reason: str | None = None):
    async with session_scope() as session:
        existing = await session.execute(
            select(BlockedUser.id).where(
                BlockedUser.chat_id == chat_id,
                BlockedUser.telegram_id == telegram_id,
            )
        )

        if existing.scalar_one_or_none() is not None:
            return

        session.add(
            BlockedUser(
                chat_id=chat_id,
                telegram_id=telegram_id,
                reason=reason,
            )
        )

        await session.commit()


async def unblock_user(chat_id: int, telegram_id: int):
    async with session_scope() as session:
        await session.execute(
            BlockedUser.__table__.delete().where(
                BlockedUser.chat_id == chat_id,
                BlockedUser.telegram_id == telegram_id,
            )
        )
        await session.commit()


async def get_blocked_ids(chat_id: int) -> set[int]:
    async with session_scope() as session:
        result = await session.execute(
            select(BlockedUser.telegram_id).where(
                BlockedUser.chat_id == chat_id
            )
        )
        return set(result.scalars().all())


# =========================================================
# ДАННЫЕ ДЛЯ ВЕБ-ПАНЕЛИ
# =========================================================

async def list_known_chats() -> list[dict]:
    """
    Все группы, где бот кого-то видел.
    """
    async with session_scope() as session:
        result = await session.execute(
            select(
                GroupMember.chat_id,
                func.count(GroupMember.id),
                func.max(GroupMember.updated_at),
            )
            .group_by(GroupMember.chat_id)
            .order_by(desc(func.max(GroupMember.updated_at)))
        )

        rows = result.all()

        if not rows:
            return []

        ids = [row[0] for row in rows]

        titles_result = await session.execute(
            select(GroupSettings.chat_id, GroupSettings.title).where(
                GroupSettings.chat_id.in_(ids)
            )
        )

        titles = dict(titles_result.all())

    fresh_after = utcnow() - timedelta(days=7)

    return [
        {
            "chat_id": chat_id,
            "title": titles.get(chat_id) or f"Группа {chat_id}",
            "members": int(members or 0),
            "last_seen": last_seen.isoformat() if last_seen else None,
            "active": bool(last_seen and last_seen >= fresh_after),
        }
        for chat_id, members, last_seen in rows
        if chat_id < 0
    ]


async def get_overview(chat_id: int | None) -> dict:
    """
    Цифры для главной: люди, сообщения, экономика.
    """
    async with session_scope() as session:
        member_query = select(
            func.count(func.distinct(GroupMember.telegram_id)),
            func.coalesce(func.sum(GroupMember.messages_count), 0),
            func.count(func.distinct(GroupMember.chat_id)),
        )

        if chat_id is not None:
            member_query = member_query.where(GroupMember.chat_id == chat_id)

        people, messages, chats = (
            await session.execute(member_query)
        ).one()

        if chat_id is None:
            economy_query = select(
                func.coalesce(func.sum(UserProfile.coins), 0),
                func.coalesce(func.sum(UserProfile.xp), 0),
            )
            coins, xp = (await session.execute(economy_query)).one()
        else:
            ids_result = await session.execute(
                select(GroupMember.telegram_id).where(
                    GroupMember.chat_id == chat_id
                )
            )
            ids = list(ids_result.scalars().all())

            if ids:
                economy_query = select(
                    func.coalesce(func.sum(UserProfile.coins), 0),
                    func.coalesce(func.sum(UserProfile.xp), 0),
                ).where(UserProfile.telegram_id.in_(ids))

                coins, xp = (await session.execute(economy_query)).one()
            else:
                coins, xp = 0, 0

        active_since = utcnow() - timedelta(days=1)

        active_query = select(
            func.count(func.distinct(GroupMember.telegram_id))
        ).where(GroupMember.updated_at >= active_since)

        if chat_id is not None:
            active_query = active_query.where(GroupMember.chat_id == chat_id)

        active = (await session.execute(active_query)).scalar() or 0

    return {
        "people": int(people or 0),
        "messages": int(messages or 0),
        "chats": int(chats or 0),
        "coins": int(coins or 0),
        "xp": int(xp or 0),
        "active_today": int(active),
    }


async def list_members(
    chat_id: int | None,
    query: str = "",
    limit: int = 50,
) -> list[dict]:
    """
    Участники с их профилями — для экрана «Пользователи».
    """
    async with session_scope() as session:
        members_query = select(
            GroupMember.telegram_id,
            func.max(GroupMember.display_name),
            func.sum(GroupMember.messages_count),
            func.max(GroupMember.updated_at),
        ).group_by(GroupMember.telegram_id)

        if chat_id is not None:
            members_query = members_query.where(
                GroupMember.chat_id == chat_id
            )

        if query:
            members_query = members_query.where(
                GroupMember.display_name.ilike(f"%{query}%")
            )

        members_query = members_query.order_by(
            desc(func.max(GroupMember.updated_at))
        ).limit(limit)

        rows = (await session.execute(members_query)).all()

        if not rows:
            return []

        ids = [row[0] for row in rows]

        profiles_result = await session.execute(
            select(UserProfile).where(UserProfile.telegram_id.in_(ids))
        )

        profiles = {
            profile.telegram_id: profile
            for profile in profiles_result.scalars().all()
        }

    people = []

    for telegram_id, name, messages, last_seen in rows:
        profile = profiles.get(telegram_id)

        people.append({
            "telegram_id": telegram_id,
            "name": name or (profile.display_name if profile else "Игрок"),
            "messages": int(messages or 0),
            "last_seen": last_seen.isoformat() if last_seen else None,
            "coins": profile.coins if profile else 0,
            "xp": profile.xp if profile else 0,
            "level": profile.level if profile else 1,
            "karma": profile.karma if profile else 0,
        })

    return people


async def get_user_card(telegram_id: int) -> dict | None:
    """
    Подробности одного человека для карточки в панели.
    """
    async with session_scope() as session:
        profile = (
            await session.execute(
                select(UserProfile).where(
                    UserProfile.telegram_id == telegram_id
                )
            )
        ).scalar_one_or_none()

        if profile is None:
            return None

        user = (
            await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
        ).scalar_one_or_none()

        items = (
            await session.execute(
                select(func.coalesce(func.sum(InventoryItem.qty), 0)).where(
                    InventoryItem.telegram_id == telegram_id
                )
            )
        ).scalar() or 0

        achievements = (
            await session.execute(
                select(func.count(UserAchievement.id)).where(
                    UserAchievement.telegram_id == telegram_id
                )
            )
        ).scalar() or 0

        chats = (
            await session.execute(
                select(func.count(func.distinct(GroupMember.chat_id))).where(
                    GroupMember.telegram_id == telegram_id
                )
            )
        ).scalar() or 0

        transactions = (
            await session.execute(
                select(Transaction)
                .where(Transaction.telegram_id == telegram_id)
                .order_by(Transaction.created_at.desc())
                .limit(10)
            )
        ).scalars().all()

    return {
        "telegram_id": telegram_id,
        "name": profile.display_name or "Игрок",
        "username": user.username if user else None,
        "coins": profile.coins,
        "xp": profile.xp,
        "level": profile.level,
        "karma": profile.karma,
        "messages": profile.messages_count,
        "games_played": profile.games_played,
        "games_won": profile.games_won,
        "best_streak": profile.best_streak,
        "items": int(items),
        "achievements": int(achievements),
        "chats": int(chats),
        "created_at": (
            profile.created_at.isoformat() if profile.created_at else None
        ),
        "updated_at": (
            profile.updated_at.isoformat() if profile.updated_at else None
        ),
        "history": [
            {
                "amount": item.amount,
                "reason": item.reason,
                "note": item.note,
                "balance_after": item.balance_after,
                "created_at": item.created_at.isoformat(),
            }
            for item in transactions
        ],
    }


# =========================================================
# СВОДКИ ДЛЯ ОСТАЛЬНЫХ ЭКРАНОВ ПАНЕЛИ
# =========================================================

async def achievements_stats() -> dict[str, int]:
    """
    Сколько человек открыло каждое достижение.
    """
    async with session_scope() as session:
        result = await session.execute(
            select(
                UserAchievement.achievement_key,
                func.count(UserAchievement.id),
            ).group_by(UserAchievement.achievement_key)
        )
        return {key: int(count) for key, count in result.all()}


async def shop_stats() -> dict[str, dict]:
    """
    Сколько каждого товара куплено и подарено.
    """
    async with session_scope() as session:
        result = await session.execute(
            select(
                InventoryItem.item_key,
                func.coalesce(func.sum(InventoryItem.qty), 0),
                func.count(InventoryItem.id).filter(
                    InventoryItem.from_telegram_id.is_not(None)
                ),
            ).group_by(InventoryItem.item_key)
        )

        return {
            key: {"total": int(total or 0), "gifted": int(gifted or 0)}
            for key, total, gifted in result.all()
        }


async def recent_transactions(chat_id: int | None, limit: int = 30):
    async with session_scope() as session:
        query = select(Transaction).order_by(Transaction.created_at.desc())

        if chat_id is not None:
            query = query.where(Transaction.chat_id == chat_id)

        rows = (await session.execute(query.limit(limit))).scalars().all()

        if not rows:
            return []

        ids = {row.telegram_id for row in rows}

        names_result = await session.execute(
            select(UserProfile.telegram_id, UserProfile.display_name).where(
                UserProfile.telegram_id.in_(ids)
            )
        )

        names = dict(names_result.all())

    return [
        {
            "telegram_id": row.telegram_id,
            "name": names.get(row.telegram_id) or "Игрок",
            "amount": row.amount,
            "reason": row.reason,
            "note": row.note,
            "balance_after": row.balance_after,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


async def media_stats(limit: int = 60) -> list[dict]:
    """
    Собранные коллекции картинок: сколько всего и сколько уже
    закэшировано в Telegram.
    """
    async with session_scope() as session:
        result = await session.execute(
            select(
                ActionImage.action,
                func.count(ActionImage.id),
                func.count(ActionImage.id).filter(
                    ActionImage.telegram_file_id.is_not(None)
                ),
                func.count(ActionImage.id).filter(ActionImage.used.is_(True)),
            )
            .group_by(ActionImage.action)
            .order_by(desc(func.count(ActionImage.id)))
            .limit(limit)
        )

        return [
            {
                "collection": action,
                "total": int(total or 0),
                "cached": int(cached or 0),
                "used": int(used or 0),
            }
            for action, total, cached, used in result.all()
        ]


async def game_stats(chat_id: int | None, days: int = 30) -> dict:
    since = utcnow() - timedelta(days=days)

    async with session_scope() as session:
        query = select(
            func.count(GameRound.id),
            func.count(GameRound.id).filter(GameRound.status == "finished"),
            func.coalesce(func.sum(GameRound.likes), 0),
        ).where(GameRound.started_at >= since)

        if chat_id is not None:
            query = query.where(GameRound.chat_id == chat_id)

        total, finished, likes = (await session.execute(query)).one()

        top_query = select(
            GameRound.winner_name,
            func.count(GameRound.id),
        ).where(
            GameRound.status == "finished",
            GameRound.winner_telegram_id.is_not(None),
            GameRound.started_at >= since,
        )

        if chat_id is not None:
            top_query = top_query.where(GameRound.chat_id == chat_id)

        top = (
            await session.execute(
                top_query.group_by(GameRound.winner_name)
                .order_by(desc(func.count(GameRound.id)))
                .limit(5)
            )
        ).all()

    return {
        "rounds": int(total or 0),
        "finished": int(finished or 0),
        "likes": int(likes or 0),
        "top": [
            {"name": name or "Игрок", "wins": int(wins)}
            for name, wins in top
        ],
    }


async def system_counts() -> dict:
    async with session_scope() as session:
        async def count(model):
            return (
                await session.execute(select(func.count(model.id)))
            ).scalar() or 0

        return {
            "users": int(await count(User)),
            "profiles": int(await count(UserProfile)),
            "chats": int(
                (
                    await session.execute(
                        select(func.count(func.distinct(GroupMember.chat_id)))
                    )
                ).scalar()
                or 0
            ),
            "transactions": int(await count(Transaction)),
            "images": int(await count(ActionImage)),
            "rounds": int(await count(GameRound)),
            "achievements": int(await count(UserAchievement)),
            "inventory": int(await count(InventoryItem)),
        }


async def top_by(field: str, chat_id: int | None, limit: int = 10):
    """
    Топ по любому полю профиля: coins, xp, karma, messages_count.
    """
    allowed = {
        "coins": UserProfile.coins,
        "xp": UserProfile.xp,
        "karma": UserProfile.karma,
        "messages_count": UserProfile.messages_count,
        "games_won": UserProfile.games_won,
    }

    column = allowed.get(field)

    if column is None:
        return []

    async with session_scope() as session:
        if chat_id is not None:
            ids_result = await session.execute(
                select(GroupMember.telegram_id).where(
                    GroupMember.chat_id == chat_id
                )
            )
            ids = list(ids_result.scalars().all())

            if not ids:
                return []

            query = select(UserProfile).where(
                UserProfile.telegram_id.in_(ids),
                column > 0,
            )
        else:
            query = select(UserProfile).where(column > 0)

        rows = (
            await session.execute(query.order_by(desc(column)).limit(limit))
        ).scalars().all()

    return [
        {
            "telegram_id": row.telegram_id,
            "name": row.display_name or "Игрок",
            "value": getattr(row, field, 0),
            "level": row.level,
        }
        for row in rows
    ]


# =========================================================
# ПРОВЕРКА ПРИНАДЛЕЖНОСТИ (для прав веб-панели)
# =========================================================

async def member_chats(telegram_id: int) -> set[int]:
    """
    В каких группах человек состоит — по данным бота.
    """
    async with session_scope() as session:
        result = await session.execute(
            select(GroupMember.chat_id).where(
                GroupMember.telegram_id == telegram_id
            )
        )
        return set(result.scalars().all())


# =========================================================
# ЖУРНАЛ
# =========================================================

async def add_audit(
    category: str,
    action: str,
    chat_id: int | None = None,
    actor_kind: str = "system",
    actor_id: int | None = None,
    actor_name: str | None = None,
    target_id: int | None = None,
    target_name: str | None = None,
    details: str | None = None,
) -> None:
    async with session_scope() as session:
        session.add(
            AuditEvent(
                chat_id=chat_id,
                actor_kind=actor_kind,
                actor_id=actor_id,
                actor_name=(actor_name or "")[:255] or None,
                target_id=target_id,
                target_name=(target_name or "")[:255] or None,
                category=category,
                action=action,
                details=(details or "")[:1000] or None,
            )
        )
        await session.commit()


async def list_audit(
    chat_ids: list[int] | None,
    category: str = "",
    query: str = "",
    target_id: int | None = None,
    limit: int = 80,
    actor_id: int | None = None,
    actor_kind: str = "",
    date_from=None,
    date_to=None,
) -> list[dict]:
    async with session_scope() as session:
        stmt = select(AuditEvent).order_by(AuditEvent.created_at.desc())

        if actor_id is not None:
            stmt = stmt.where(AuditEvent.actor_id == actor_id)

        if actor_kind:
            stmt = stmt.where(AuditEvent.actor_kind == actor_kind)

        if date_from is not None:
            stmt = stmt.where(AuditEvent.created_at >= date_from)

        if date_to is not None:
            stmt = stmt.where(AuditEvent.created_at < date_to)

        if chat_ids is not None:
            stmt = stmt.where(
                (AuditEvent.chat_id.in_(chat_ids)) | (AuditEvent.chat_id.is_(None))
            )

        if category:
            stmt = stmt.where(AuditEvent.category == category)

        if target_id is not None:
            stmt = stmt.where(AuditEvent.target_id == target_id)

        if query:
            like = f"%{query}%"
            stmt = stmt.where(
                AuditEvent.actor_name.ilike(like)
                | AuditEvent.target_name.ilike(like)
                | AuditEvent.details.ilike(like)
                | AuditEvent.action.ilike(like)
            )

        rows = (await session.execute(stmt.limit(limit))).scalars().all()

    return [
        {
            "id": row.id,
            "chat_id": row.chat_id,
            "actor_kind": row.actor_kind,
            "actor_id": row.actor_id,
            "actor_name": row.actor_name,
            "target_id": row.target_id,
            "target_name": row.target_name,
            "category": row.category,
            "action": row.action,
            "details": row.details,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


# =========================================================
# ПРЕДУПРЕЖДЕНИЯ
# =========================================================

async def add_warning(chat_id: int, telegram_id: int, reason: str | None) -> int:
    """Выдаёт предупреждение и возвращает, сколько их теперь за 30 дней."""
    async with session_scope() as session:
        session.add(ChatWarning(chat_id=chat_id, telegram_id=telegram_id, reason=reason))
        await session.commit()

    return await count_warnings(chat_id, telegram_id)


async def count_warnings(chat_id: int, telegram_id: int, days: int = 30) -> int:
    since = utcnow() - timedelta(days=days)

    async with session_scope() as session:
        return (
            await session.execute(
                select(func.count(ChatWarning.id)).where(
                    ChatWarning.chat_id == chat_id,
                    ChatWarning.telegram_id == telegram_id,
                    ChatWarning.created_at >= since,
                )
            )
        ).scalar() or 0


async def clear_warnings(chat_id: int, telegram_id: int) -> None:
    async with session_scope() as session:
        await session.execute(
            ChatWarning.__table__.delete().where(
                ChatWarning.chat_id == chat_id,
                ChatWarning.telegram_id == telegram_id,
            )
        )
        await session.commit()


async def recent_violators(chat_id: int | None, chat_ids: list[int], limit: int = 10):
    since = utcnow() - timedelta(days=7)

    async with session_scope() as session:
        stmt = (
            select(ChatWarning.telegram_id, ChatWarning.chat_id, func.count(ChatWarning.id))
            .where(ChatWarning.created_at >= since)
            .group_by(ChatWarning.telegram_id, ChatWarning.chat_id)
            .order_by(desc(func.count(ChatWarning.id)))
            .limit(limit)
        )

        if chat_id is not None:
            stmt = stmt.where(ChatWarning.chat_id == chat_id)
        else:
            stmt = stmt.where(ChatWarning.chat_id.in_(chat_ids))

        rows = (await session.execute(stmt)).all()

        if not rows:
            return []

        names = dict(
            (
                await session.execute(
                    select(UserProfile.telegram_id, UserProfile.display_name).where(
                        UserProfile.telegram_id.in_({r[0] for r in rows})
                    )
                )
            ).all()
        )

    return [
        {"telegram_id": uid, "chat_id": cid, "name": names.get(uid) or "Игрок", "warnings": int(n)}
        for uid, cid, n in rows
    ]


# =========================================================
# РОЛИ
# =========================================================

async def get_role(chat_id: int, telegram_id: int) -> str | None:
    async with session_scope() as session:
        return (
            await session.execute(
                select(AdminRole.role).where(
                    AdminRole.chat_id == chat_id,
                    AdminRole.telegram_id == telegram_id,
                )
            )
        ).scalar_one_or_none()


async def set_role(chat_id: int, telegram_id: int, role: str | None) -> None:
    async with session_scope() as session:
        await session.execute(
            AdminRole.__table__.delete().where(
                AdminRole.chat_id == chat_id,
                AdminRole.telegram_id == telegram_id,
            )
        )

        if role:
            session.add(AdminRole(chat_id=chat_id, telegram_id=telegram_id, role=role))

        await session.commit()


async def list_roles(chat_id: int) -> dict[int, str]:
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(AdminRole.telegram_id, AdminRole.role).where(
                    AdminRole.chat_id == chat_id
                )
            )
        ).all()

    return {uid: role for uid, role in rows}


# =========================================================
# ДЕЙСТВИЯ: ВКЛ/ВЫКЛ И СТАТИСТИКА
# =========================================================

async def disabled_actions(chat_id: int) -> set[str]:
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(ActionToggle.action_key).where(
                    ActionToggle.chat_id == chat_id,
                    ActionToggle.enabled.is_(False),
                )
            )
        ).scalars().all()

    return set(rows)


async def set_action_enabled(chat_id: int, action_key: str, enabled: bool) -> None:
    async with session_scope() as session:
        await session.execute(
            ActionToggle.__table__.delete().where(
                ActionToggle.chat_id == chat_id,
                ActionToggle.action_key == action_key,
            )
        )

        if not enabled:
            session.add(ActionToggle(chat_id=chat_id, action_key=action_key, enabled=False))

        await session.commit()


async def bump_action_usage(chat_id: int, action_key: str) -> None:
    day = _day_key()

    async with session_scope() as session:
        item = (
            await session.execute(
                select(ActionUsage).where(
                    ActionUsage.chat_id == chat_id,
                    ActionUsage.action_key == action_key,
                    ActionUsage.day == day,
                )
            )
        ).scalar_one_or_none()

        if item is None:
            session.add(ActionUsage(chat_id=chat_id, action_key=action_key, day=day, count=1))
        else:
            item.count += 1

        await session.commit()


async def action_usage_stats(chat_id: int | None, days: int = 7) -> dict[str, int]:
    since = (utcnow() - timedelta(days=days - 1)).strftime("%Y-%m-%d")

    async with session_scope() as session:
        stmt = select(ActionUsage.action_key, func.sum(ActionUsage.count)).where(
            ActionUsage.day >= since
        )

        if chat_id is not None:
            stmt = stmt.where(ActionUsage.chat_id == chat_id)

        rows = (await session.execute(stmt.group_by(ActionUsage.action_key))).all()

    return {key: int(total or 0) for key, total in rows}


# =========================================================
# ТЕПЛОВАЯ КАРТА
# =========================================================

async def bump_hourly(chat_id: int) -> None:
    """Atomically increment the per-group hourly message counter.

    The unique key (chat_id, day, hour) is intentionally handled with a
    PostgreSQL UPSERT.  A SELECT-then-INSERT sequence is race-prone when two
    messages arrive concurrently and can raise uq_hourly_stat.
    """
    now = utcnow()
    day, hour = now.strftime("%Y-%m-%d"), now.hour

    async with session_scope() as session:
        stmt = pg_insert(HourlyStat).values(
            chat_id=chat_id,
            day=day,
            hour=hour,
            messages=1,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_hourly_stat",
            set_={"messages": HourlyStat.messages + 1},
        )
        await session.execute(stmt)
        await session.commit()


async def heatmap(chat_id: int | None, days: int = 28, offset: int = 0) -> list[list[int]]:
    """
    Матрица 7×24: день недели (пн=0) × час. Хранится по UTC,
    offset сдвигает в часовой пояс группы (с переходом через полночь).
    """
    since = (utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    async with session_scope() as session:
        stmt = select(HourlyStat.day, HourlyStat.hour, func.sum(HourlyStat.messages)).where(
            HourlyStat.day >= since
        )

        if chat_id is not None:
            stmt = stmt.where(HourlyStat.chat_id == chat_id)

        rows = (await session.execute(stmt.group_by(HourlyStat.day, HourlyStat.hour))).all()

    grid = [[0] * 24 for _ in range(7)]

    from datetime import datetime as _dt

    for day, hour, count in rows:
        weekday = _dt.strptime(day, "%Y-%m-%d").weekday()
        shifted = hour + offset
        weekday = (weekday + shifted // 24) % 7
        grid[weekday][shifted % 24] += int(count or 0)

    return grid


# =========================================================
# РАССЫЛКИ
# =========================================================

async def create_broadcast(
    author_id: int,
    author_name: str | None,
    chat_ids: list[int],
    text: str,
    photo: str | None,
    buttons: list,
    send_at,
    media_type: str = "photo",
    mode: str = "groups",
    segment: dict | None = None,
) -> int:
    async with session_scope() as session:
        item = Broadcast(
            mode=mode,
            segment=segment or {},
            author_id=author_id,
            author_name=author_name,
            chat_ids=chat_ids,
            text=text,
            photo=photo,
            media_type=media_type,
            buttons=buttons,
            send_at=send_at,
            status="scheduled",
        )
        session.add(item)
        await session.commit()
        return item.id


async def due_broadcasts() -> list:
    async with session_scope() as session:
        return list(
            (
                await session.execute(
                    select(Broadcast).where(
                        Broadcast.status == "scheduled",
                        Broadcast.send_at <= utcnow(),
                    )
                )
            ).scalars().all()
        )


async def finish_broadcast(broadcast_id: int, sent: int, failed: int) -> None:
    async with session_scope() as session:
        await session.execute(
            update(Broadcast)
            .where(Broadcast.id == broadcast_id)
            .values(
                status="sent" if sent else "failed",
                sent=sent,
                failed=failed,
            )
        )
        await session.commit()


async def cancel_broadcast(broadcast_id: int, author_id: int | None) -> bool:
    async with session_scope() as session:
        stmt = update(Broadcast).where(
            Broadcast.id == broadcast_id,
            Broadcast.status == "scheduled",
        )

        if author_id is not None:
            stmt = stmt.where(Broadcast.author_id == author_id)

        result = await session.execute(stmt.values(status="cancelled"))
        await session.commit()

        return (result.rowcount or 0) > 0


async def list_broadcasts(chat_ids: list[int] | None, limit: int = 30) -> list[dict]:
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(Broadcast).order_by(Broadcast.created_at.desc()).limit(limit * 3)
            )
        ).scalars().all()

    items = []

    for row in rows:
        if chat_ids is not None and not set(row.chat_ids or []) & set(chat_ids):
            continue

        items.append({
            "id": row.id,
            "author": row.author_name,
            "chats": len(row.chat_ids or []),
            "text": row.text,
            "has_photo": bool(row.photo),
            "media_type": row.media_type or "photo",
            "mode": row.mode or "groups",
            "segment": row.segment or {},
            "buttons": row.buttons or [],
            "send_at": row.send_at.isoformat(),
            "status": row.status,
            "sent": row.sent,
            "failed": row.failed,
        })

        if len(items) >= limit:
            break

    return items


# =========================================================
# ПОИСК ПО ЛЮДЯМ
# =========================================================

async def search_people(query: str, chat_ids: list[int] | None, limit: int = 8):
    async with session_scope() as session:
        stmt = select(User)

        if query.lstrip("-").isdigit():
            stmt = stmt.where(User.telegram_id == int(query))
        else:
            like = f"%{query.lstrip('@')}%"
            stmt = stmt.where(User.first_name.ilike(like) | User.username.ilike(like))

        users = (await session.execute(stmt.limit(limit * 4))).scalars().all()

        if chat_ids is not None and users:
            allowed = set(
                (
                    await session.execute(
                        select(GroupMember.telegram_id).where(
                            GroupMember.chat_id.in_(chat_ids),
                            GroupMember.telegram_id.in_([u.telegram_id for u in users]),
                        )
                    )
                ).scalars().all()
            )
            users = [u for u in users if u.telegram_id in allowed]

    return [
        {"telegram_id": u.telegram_id, "name": u.first_name or u.username or "Игрок", "username": u.username}
        for u in users[:limit]
    ]


async def today_counters(chat_id: int | None, chat_ids: list[int]) -> dict:
    day = _day_key()

    async with session_scope() as session:
        stmt = select(
            func.coalesce(func.sum(DailyStat.messages), 0),
            func.coalesce(func.sum(DailyStat.actions), 0),
            func.coalesce(func.sum(DailyStat.games), 0),
            func.coalesce(func.sum(DailyStat.new_users), 0),
            func.coalesce(func.sum(DailyStat.warnings), 0),
            func.coalesce(func.sum(DailyStat.mutes), 0),
            func.coalesce(func.sum(DailyStat.bans), 0),
            func.coalesce(func.sum(DailyStat.deleted), 0),
            func.coalesce(func.sum(DailyStat.ai_requests), 0),
            func.coalesce(func.sum(DailyStat.xp), 0),
            func.coalesce(func.sum(DailyStat.images), 0),
            func.coalesce(func.sum(DailyStat.active_users), 0),
        ).where(DailyStat.day == day)

        if chat_id is not None:
            stmt = stmt.where(DailyStat.chat_id == chat_id)
        else:
            stmt = stmt.where(DailyStat.chat_id.in_(chat_ids))

        row = (await session.execute(stmt)).one()

        coins_stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.amount > 0,
            Transaction.created_at >= utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
        )

        if chat_id is not None:
            coins_stmt = coins_stmt.where(Transaction.chat_id == chat_id)
        else:
            coins_stmt = coins_stmt.where(Transaction.chat_id.in_(chat_ids))

        coins = (await session.execute(coins_stmt)).scalar() or 0

        today_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        gifts_stmt = select(func.count(Transaction.id)).where(
            Transaction.reason == "gift_out", Transaction.created_at >= today_start,
        )

        if chat_id is not None:
            gifts_stmt = gifts_stmt.where(Transaction.chat_id == chat_id)
        else:
            gifts_stmt = gifts_stmt.where(Transaction.chat_id.in_(chat_ids))

        gifts = (await session.execute(gifts_stmt)).scalar() or 0

    keys = ("messages", "actions", "games", "new_users", "warnings",
            "mutes", "bans", "deleted", "ai_requests", "xp", "images", "active_users")

    result = {key: int(value or 0) for key, value in zip(keys, row)}
    result["coins"] = int(coins)
    result["gifts"] = int(gifts)

    return result


async def action_file_id(action_key: str) -> str | None:
    """Любая уже загруженная в Telegram картинка действия — для превью."""
    async with session_scope() as session:
        return (
            await session.execute(
                select(ActionImage.telegram_file_id)
                .where(
                    ActionImage.telegram_file_id.is_not(None),
                    ActionImage.action.like(f"%/{action_key}#%")
                    | ActionImage.action.like(f"%/{action_key}:%"),
                )
                .limit(1)
            )
        ).scalar_one_or_none()


# =========================================================
# ПРАВКИ ДЕЙСТВИЙ ДЛЯ ГРУППЫ
# =========================================================

async def list_action_custom(chat_id: int, action_key: str | None = None) -> list:
    async with session_scope() as session:
        stmt = select(ActionCustom).where(ActionCustom.chat_id == chat_id)

        if action_key:
            stmt = stmt.where(ActionCustom.action_key == action_key)

        return list((await session.execute(stmt.order_by(ActionCustom.id))).scalars().all())


async def add_action_custom(chat_id: int, action_key: str, kind: str, value: str,
                            author_id: int | None = None) -> int:
    async with session_scope() as session:
        item = ActionCustom(chat_id=chat_id, action_key=action_key, kind=kind,
                            value=value, author_id=author_id)
        session.add(item)
        await session.commit()
        return item.id


async def set_action_custom_single(chat_id: int, action_key: str, kind: str,
                                   value: str | None, author_id: int | None = None) -> None:
    """Для одиночных значений (cooldown, image_mode): заменить или убрать."""
    async with session_scope() as session:
        await session.execute(
            ActionCustom.__table__.delete().where(
                ActionCustom.chat_id == chat_id,
                ActionCustom.action_key == action_key,
                ActionCustom.kind == kind,
            )
        )

        if value is not None:
            session.add(ActionCustom(chat_id=chat_id, action_key=action_key,
                                     kind=kind, value=value, author_id=author_id))

        await session.commit()


async def delete_action_custom(chat_id: int, custom_id: int) -> dict | None:
    async with session_scope() as session:
        item = (
            await session.execute(
                select(ActionCustom).where(
                    ActionCustom.id == custom_id,
                    ActionCustom.chat_id == chat_id,
                )
            )
        ).scalar_one_or_none()

        if item is None:
            return None

        info = {"kind": item.kind, "action_key": item.action_key, "value": item.value}

        await session.delete(item)
        await session.commit()

        return info


async def unhide_action_image(chat_id: int, action_key: str, image_id: int) -> None:
    async with session_scope() as session:
        await session.execute(
            ActionCustom.__table__.delete().where(
                ActionCustom.chat_id == chat_id,
                ActionCustom.action_key == action_key,
                ActionCustom.kind == "hide_image",
                ActionCustom.value == str(image_id),
            )
        )
        await session.commit()


async def remember_custom_file_id(custom_id: int, file_id: str) -> None:
    async with session_scope() as session:
        await session.execute(
            update(ActionCustom)
            .where(ActionCustom.id == custom_id)
            .values(file_id=file_id, shows=ActionCustom.shows + 1, last_used_at=utcnow())
        )
        await session.commit()


async def bump_custom_shows(custom_id: int) -> None:
    async with session_scope() as session:
        await session.execute(
            update(ActionCustom)
            .where(ActionCustom.id == custom_id)
            .values(shows=ActionCustom.shows + 1, last_used_at=utcnow())
        )
        await session.commit()


async def get_action_custom(custom_id: int):
    async with session_scope() as session:
        return (
            await session.execute(select(ActionCustom).where(ActionCustom.id == custom_id))
        ).scalar_one_or_none()


async def action_pool_images(action_key: str, limit: int = 40) -> list[dict]:
    """Картинки общей коллекции действия (все варианты пар)."""
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(ActionImage)
                .where(
                    ActionImage.action.like(f"%/{action_key}#%")
                    | ActionImage.action.like(f"%/{action_key}:%")
                )
                .order_by(ActionImage.id.desc())
                .limit(limit)
            )
        ).scalars().all()

    return [
        {
            "id": row.id,
            "collection": row.action,
            "provider": getattr(row, "provider", None) or row.action.split("/", 1)[0],
            "photo_id": row.photo_id,
            "cached": bool(row.telegram_file_id),
            "used": bool(row.used),
            "used_at": row.used_at.isoformat() if row.used_at else None,
        }
        for row in rows
    ]


async def get_action_image_row(image_id: int):
    async with session_scope() as session:
        return (
            await session.execute(select(ActionImage).where(ActionImage.id == image_id))
        ).scalar_one_or_none()


# =========================================================
# УЧАСТНИКИ: СЧЁТЧИКИ, VIP, ВХОД/ВЫХОД
# =========================================================

async def bump_member_counter(chat_id: int, telegram_id: int, field: str) -> None:
    if field not in ("actions_count", "ai_count"):
        return

    async with session_scope() as session:
        await session.execute(
            update(GroupMember)
            .where(GroupMember.chat_id == chat_id, GroupMember.telegram_id == telegram_id)
            .values({field: getattr(GroupMember, field) + 1})
        )
        await session.commit()


async def set_member_vip(chat_id: int, telegram_id: int, vip: bool) -> bool:
    async with session_scope() as session:
        result = await session.execute(
            update(GroupMember)
            .where(GroupMember.chat_id == chat_id, GroupMember.telegram_id == telegram_id)
            .values(vip=vip)
        )
        await session.commit()
        return (result.rowcount or 0) > 0


async def mark_member_left(chat_id: int, telegram_id: int, left: bool) -> None:
    async with session_scope() as session:
        await session.execute(
            update(GroupMember)
            .where(GroupMember.chat_id == chat_id, GroupMember.telegram_id == telegram_id)
            .values(left_at=utcnow() if left else None)
        )
        await session.commit()


MEMBER_SORTS = {
    "activity": "last_seen",
    "messages": "messages",
    "xp": "xp",
    "coins": "coins",
    "karma": "karma",
    "level": "level",
    "warnings": "warnings",
    "joined": "joined",
}


def select_members(items: list[dict], flt: str, sort: str, query: str, now) -> list[dict]:
    """
    Фильтр, поиск и сортировка участников. Чистая функция — без
    базы, её проверяют тесты.
    """
    needle = (query or "").lower().lstrip("@")
    people = []

    for item in items:
        if needle:
            haystack = f"{item['name']} {item.get('username') or ''} {item['telegram_id']}".lower()
            if needle not in haystack:
                continue

        seen = item.get("last_seen")
        idle = (now - seen).days if seen else 9999
        joined = item.get("joined")
        fresh = joined is not None and (now - joined).days < 7
        left = item.get("left", False)

        keep = {
            "all": not left,
            "active": idle < 1 and not left,
            "new": fresh and not left,
            "vip": item.get("vip", False),
            "violators": item.get("warnings", 0) > 0,
            "admins": item.get("admin", False),
            "inactive30": idle >= 30 and not left,
            "inactive90": idle >= 90 and not left,
            "ignored": item.get("blocked", False),
            "left": left,
        }.get(flt, not left)

        if keep:
            people.append(item)

    field = MEMBER_SORTS.get(sort, "last_seen")
    old = datetime.min

    if field in ("joined", "last_seen"):
        people.sort(key=lambda p: p.get(field) or old, reverse=True)
    else:
        people.sort(key=lambda p: p.get(field) or 0, reverse=True)

    return people


async def members_page(
    chat_ids: list[int],
    query: str = "",
    flt: str = "all",
    sort: str = "activity",
    admin_ids: set[int] | None = None,
    limit: int = 40,
    offset: int = 0,
) -> dict:
    """
    Участники с фильтрами и сортировкой. Считается в памяти после
    одной выборки: групп и людей немного, а так фильтры по разным
    таблицам (профиль, предупреждения, админы) остаются простыми.
    """
    now = utcnow()

    async with session_scope() as session:
        rows = (
            await session.execute(
                select(GroupMember).where(GroupMember.chat_id.in_(chat_ids))
            )
        ).scalars().all()

        if not rows:
            return {"users": [], "total": 0}

        ids = {row.telegram_id for row in rows}

        profiles = {
            p.telegram_id: p
            for p in (
                await session.execute(select(UserProfile).where(UserProfile.telegram_id.in_(ids)))
            ).scalars().all()
        }

        users = {
            u.telegram_id: u
            for u in (
                await session.execute(select(User).where(User.telegram_id.in_(ids)))
            ).scalars().all()
        }

        since = now - timedelta(days=30)

        warnings = dict(
            (
                await session.execute(
                    select(ChatWarning.telegram_id, func.count(ChatWarning.id))
                    .where(ChatWarning.chat_id.in_(chat_ids), ChatWarning.created_at >= since)
                    .group_by(ChatWarning.telegram_id)
                )
            ).all()
        )

        blocked = set(
            (
                await session.execute(
                    select(BlockedUser.telegram_id).where(BlockedUser.chat_id.in_(chat_ids))
                )
            ).scalars().all()
        )

    # Один человек может быть в нескольких группах — сводим
    merged: dict[int, dict] = {}

    for row in rows:
        item = merged.setdefault(row.telegram_id, {
            "telegram_id": row.telegram_id,
            "name": row.display_name,
            "messages": 0,
            "last_seen": None,
            "joined": None,
            "vip": False,
            "left": True,
        })

        item["messages"] += row.messages_count or 0
        item["vip"] = item["vip"] or bool(row.vip)
        item["left"] = item["left"] and row.left_at is not None

        if row.updated_at and (item["last_seen"] is None or row.updated_at > item["last_seen"]):
            item["last_seen"] = row.updated_at
            item["name"] = row.display_name or item["name"]

        if row.joined_at and (item["joined"] is None or row.joined_at < item["joined"]):
            item["joined"] = row.joined_at

    for uid, item in merged.items():
        profile = profiles.get(uid)
        user = users.get(uid)

        item.update({
            "username": user.username if user else None,
            "coins": profile.coins if profile else 0,
            "xp": profile.xp if profile else 0,
            "level": profile.level if profile else 1,
            "karma": profile.karma if profile else 0,
            "warnings": int(warnings.get(uid, 0)),
            "blocked": uid in blocked,
            "admin": uid in (admin_ids or set()),
        })

        item["name"] = item["name"] or (profile.display_name if profile else None) or (user.first_name if user else None) or "Игрок"

    people = select_members(list(merged.values()), flt, sort, query, now)

    total = len(people)
    page = people[offset: offset + limit]

    for item in page:
        item["last_seen"] = item["last_seen"].isoformat() if item["last_seen"] else None
        item["joined"] = item["joined"].isoformat() if item["joined"] else None

    return {"users": page, "total": total}


async def member_profile(telegram_id: int, chat_ids: list[int]) -> dict:
    """То, что о человеке знает группа (или группы админа)."""
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(GroupMember).where(
                    GroupMember.telegram_id == telegram_id,
                    GroupMember.chat_id.in_(chat_ids),
                )
            )
        ).scalars().all()

        warnings = (
            await session.execute(
                select(func.count(ChatWarning.id)).where(
                    ChatWarning.telegram_id == telegram_id,
                    ChatWarning.chat_id.in_(chat_ids),
                    ChatWarning.created_at >= utcnow() - timedelta(days=30),
                )
            )
        ).scalar() or 0

        audit_counts = dict(
            (
                await session.execute(
                    select(AuditEvent.action, func.count(AuditEvent.id))
                    .where(
                        AuditEvent.target_id == telegram_id,
                        AuditEvent.chat_id.in_(chat_ids),
                        AuditEvent.category == "moderation",
                    )
                    .group_by(AuditEvent.action)
                )
            ).all()
        )

        achievements = (
            await session.execute(
                select(UserAchievement.achievement_key, UserAchievement.created_at)
                .where(UserAchievement.telegram_id == telegram_id)
                .order_by(UserAchievement.created_at.desc())
            )
        ).all()

    joined = min((r.joined_at for r in rows if r.joined_at), default=None)
    seen = max((r.updated_at for r in rows if r.updated_at), default=None)

    return {
        "joined": joined.isoformat() if joined else None,
        "last_seen": seen.isoformat() if seen else None,
        "group_messages": sum(r.messages_count or 0 for r in rows),
        "actions": sum(r.actions_count or 0 for r in rows),
        "ai_requests": sum(r.ai_count or 0 for r in rows),
        "games": sum(r.games_played or 0 for r in rows),
        "vip": any(r.vip for r in rows),
        "left": bool(rows) and all(r.left_at is not None for r in rows),
        "warnings": int(warnings),
        "violations": int(audit_counts.get("violation", 0)),
        "mutes": int(audit_counts.get("mute", 0)),
        "bans": int(audit_counts.get("ban", 0) + audit_counts.get("tempban", 0)),
        "achievements": [
            {"key": key, "at": at.isoformat() if at else None}
            for key, at in achievements
        ],
    }


async def user_history(telegram_id: int, chat_ids: list[int], limit: int = 40) -> list[dict]:
    """
    Всё, что происходило с человеком, одной лентой: вход и выход,
    модерация, баланс, достижения.
    """
    async with session_scope() as session:
        events = (
            await session.execute(
                select(AuditEvent)
                .where(
                    AuditEvent.target_id == telegram_id,
                    (AuditEvent.chat_id.in_(chat_ids)) | (AuditEvent.chat_id.is_(None)),
                )
                .order_by(AuditEvent.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()

        money = (
            await session.execute(
                select(Transaction)
                .where(Transaction.telegram_id == telegram_id)
                .order_by(Transaction.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()

        achievements = (
            await session.execute(
                select(UserAchievement)
                .where(UserAchievement.telegram_id == telegram_id)
                .order_by(UserAchievement.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()

    items = []

    for e in events:
        # Изменения баланса админом уже есть в операциях — не дублируем
        if e.category == "economy" and e.action == "coins":
            continue

        items.append({
            "type": e.category, "action": e.action,
            "actor": e.actor_name if e.actor_kind == "admin" else ("Мара" if e.actor_kind == "bot" else None),
            "details": e.details, "at": e.created_at.isoformat(),
        })

    for t in money:
        items.append({
            "type": "money", "action": t.reason, "amount": t.amount,
            "details": t.note, "at": t.created_at.isoformat(),
        })

    for a in achievements:
        items.append({
            "type": "achievement", "action": a.achievement_key,
            "at": a.created_at.isoformat() if a.created_at else "",
        })

    items.sort(key=lambda i: i["at"], reverse=True)

    return items[:limit]


# =========================================================
# МАГАЗИН: ПРАВИЛА ГРУППЫ
# =========================================================

async def list_shop_overrides(chat_id: int) -> list:
    async with session_scope() as session:
        return list(
            (await session.execute(select(ShopOverride).where(ShopOverride.chat_id == chat_id))).scalars().all()
        )


async def set_shop_override(chat_id: int, item_key: str, price: int | None,
                            enabled: bool, stock: int | None) -> None:
    async with session_scope() as session:
        await session.execute(
            ShopOverride.__table__.delete().where(
                ShopOverride.chat_id == chat_id, ShopOverride.item_key == item_key,
            )
        )

        # Всё по умолчанию — запись не нужна
        if price is not None or not enabled or stock is not None:
            session.add(ShopOverride(chat_id=chat_id, item_key=item_key,
                                     price=price, enabled=enabled, stock=stock))

        await session.commit()


async def take_from_stock(chat_id: int, item_key: str) -> bool:
    """
    Списать одну штуку со склада. Атомарно: два покупателя
    одновременно не заберут последнюю вещь дважды.
    """
    async with session_scope() as session:
        result = await session.execute(
            update(ShopOverride)
            .where(
                ShopOverride.chat_id == chat_id,
                ShopOverride.item_key == item_key,
                ShopOverride.stock.is_not(None),
                ShopOverride.stock > 0,
            )
            .values(stock=ShopOverride.stock - 1)
        )
        await session.commit()
        return (result.rowcount or 0) > 0


async def return_to_stock(chat_id: int, item_key: str) -> None:
    async with session_scope() as session:
        await session.execute(
            update(ShopOverride)
            .where(
                ShopOverride.chat_id == chat_id,
                ShopOverride.item_key == item_key,
                ShopOverride.stock.is_not(None),
            )
            .values(stock=ShopOverride.stock + 1)
        )
        await session.commit()


async def shop_purchases(chat_ids: list[int], limit: int = 40) -> list[dict]:
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(Transaction)
                .where(
                    Transaction.chat_id.in_(chat_ids),
                    Transaction.reason.in_(("purchase", "gift_out")),
                )
                .order_by(Transaction.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()

        names = {}

        if rows:
            names = dict(
                (
                    await session.execute(
                        select(UserProfile.telegram_id, UserProfile.display_name).where(
                            UserProfile.telegram_id.in_({r.telegram_id for r in rows})
                        )
                    )
                ).all()
            )

    return [
        {
            "name": names.get(r.telegram_id) or "Игрок",
            "telegram_id": r.telegram_id,
            "amount": r.amount,
            "note": r.note,
            "gift": r.reason == "gift_out",
            "at": r.created_at.isoformat(),
        }
        for r in rows
    ]


# =========================================================
# ЭКОНОМИКА: СВОДКА И МАССОВЫЕ ИЗМЕНЕНИЯ
# =========================================================

async def economy_flow(chat_ids: list[int], days: int = 1) -> dict:
    """Сколько выдано и потрачено, и за что — по причинам."""
    since = utcnow() - timedelta(days=days)

    async with session_scope() as session:
        rows = (
            await session.execute(
                select(Transaction.reason, func.sum(Transaction.amount), func.count(Transaction.id))
                .where(Transaction.chat_id.in_(chat_ids), Transaction.created_at >= since)
                .group_by(Transaction.reason)
            )
        ).all()

    issued = sum(int(total) for _r, total, _n in rows if total and total > 0)
    spent = -sum(int(total) for _r, total, _n in rows if total and total < 0)

    return {
        "issued": issued,
        "spent": spent,
        "by_reason": sorted(
            [{"reason": r, "total": int(t or 0), "count": int(n)} for r, t, n in rows],
            key=lambda x: abs(x["total"]), reverse=True,
        ),
    }


async def audience_ids(chat_id: int, audience: str, level_min: int = 0) -> list[int]:
    """Кому применить массовое изменение."""
    now = utcnow()

    async with session_scope() as session:
        rows = (
            await session.execute(
                select(GroupMember).where(
                    GroupMember.chat_id == chat_id,
                    GroupMember.left_at.is_(None),
                )
            )
        ).scalars().all()

        levels = {}

        if audience == "level":
            levels = dict(
                (
                    await session.execute(
                        select(UserProfile.telegram_id, UserProfile.level).where(
                            UserProfile.telegram_id.in_([r.telegram_id for r in rows])
                        )
                    )
                ).all()
            )

    result = []

    for row in rows:
        if audience == "active" and (not row.updated_at or (now - row.updated_at).days >= 7):
            continue
        if audience == "vip" and not row.vip:
            continue
        if audience == "level" and levels.get(row.telegram_id, 1) < level_min:
            continue
        result.append(row.telegram_id)

    return result


async def recent_votes(chat_ids: list[int], limit: int = 30) -> list[dict]:
    """
    Последние голоса рейтинга среди людей из групп админа
    (сами голоса хранятся без группы).
    """
    async with session_scope() as session:
        members = set(
            (
                await session.execute(
                    select(GroupMember.telegram_id).where(GroupMember.chat_id.in_(chat_ids))
                )
            ).scalars().all()
        )

        if not members:
            return []

        rows = (
            await session.execute(
                select(RatingVote)
                .where(RatingVote.target_telegram_id.in_(members))
                .order_by(RatingVote.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()

        ids = {r.giver_telegram_id for r in rows} | {r.target_telegram_id for r in rows}

        names = dict(
            (
                await session.execute(
                    select(UserProfile.telegram_id, UserProfile.display_name).where(
                        UserProfile.telegram_id.in_(ids)
                    )
                )
            ).all()
        ) if ids else {}

    return [
        {
            "giver": names.get(r.giver_telegram_id) or "Игрок",
            "target": names.get(r.target_telegram_id) or "Игрок",
            "target_id": r.target_telegram_id,
            "amount": r.amount,
            "at": r.created_at.isoformat(),
        }
        for r in rows
    ]


# =========================================================
# ПАМЯТЬ МАРЫ: СРОК ХРАНЕНИЯ И ОЧИСТКА
# =========================================================

async def memory_stats(chat_id: int) -> dict:
    async with session_scope() as session:
        count, oldest = (
            await session.execute(
                select(func.count(MessageMemory.id), func.min(MessageMemory.created_at))
                .where(MessageMemory.chat_id == chat_id)
            )
        ).one()

    return {"messages": int(count or 0), "oldest": oldest.isoformat() if oldest else None}


async def clear_memory(chat_id: int) -> int:
    async with session_scope() as session:
        result = await session.execute(
            MessageMemory.__table__.delete().where(MessageMemory.chat_id == chat_id)
        )
        await session.commit()
        return result.rowcount or 0


async def expire_memory(chat_id: int, days: int) -> int:
    """
    Удаляет сообщения старше срока. Статистику по дням это не трогает:
    она к этому моменту уже перенесена в daily_stats.
    """
    cutoff = utcnow() - timedelta(days=max(days, 1))

    async with session_scope() as session:
        result = await session.execute(
            MessageMemory.__table__.delete().where(
                MessageMemory.chat_id == chat_id,
                MessageMemory.created_at < cutoff,
            )
        )
        await session.commit()
        return result.rowcount or 0


async def memory_chat_ids() -> list[int]:
    async with session_scope() as session:
        return list(
            (await session.execute(select(func.distinct(MessageMemory.chat_id)))).scalars().all()
        )


# =========================================================
# АВТООТВЕТЫ
# =========================================================

async def list_autoreplies(chat_id: int) -> list:
    async with session_scope() as session:
        return list(
            (await session.execute(
                select(AutoReply).where(AutoReply.chat_id == chat_id).order_by(AutoReply.id)
            )).scalars().all()
        )


async def save_autoreply(chat_id: int, data: dict, reply_id: int | None = None) -> int:
    async with session_scope() as session:
        if reply_id:
            item = (
                await session.execute(
                    select(AutoReply).where(AutoReply.id == reply_id, AutoReply.chat_id == chat_id)
                )
            ).scalar_one_or_none()

            if item is None:
                return 0
        else:
            item = AutoReply(chat_id=chat_id)
            session.add(item)

        for field in ("trigger", "response", "match", "probability", "cooldown", "enabled"):
            if field in data:
                setattr(item, field, data[field])

        await session.commit()
        return item.id


async def delete_autoreply(chat_id: int, reply_id: int) -> bool:
    async with session_scope() as session:
        result = await session.execute(
            AutoReply.__table__.delete().where(AutoReply.id == reply_id, AutoReply.chat_id == chat_id)
        )
        await session.commit()
        return (result.rowcount or 0) > 0


async def bump_autoreply(reply_id: int) -> None:
    async with session_scope() as session:
        await session.execute(
            update(AutoReply).where(AutoReply.id == reply_id).values(hits=AutoReply.hits + 1)
        )
        await session.commit()


# =========================================================
# АНАЛИТИКА ЗА ПЕРИОД
# =========================================================

def compare(current: int, previous: int) -> int | None:
    """Изменение в процентах к прошлому периоду. None — сравнивать не с чем."""
    if not previous:
        return None
    return round((current - previous) * 100 / previous)


async def analytics_summary(chat_ids: list[int], days: int, offset: int = 0) -> dict:
    now = utcnow()
    start = now - timedelta(days=days)
    prev_start = start - timedelta(days=days)

    day_from = (now - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    prev_from = (now - timedelta(days=2 * days - 1)).strftime("%Y-%m-%d")

    columns = [getattr(DailyStat, f) for f in DAILY_FIELDS]

    async with session_scope() as session:
        rows = (
            await session.execute(
                select(DailyStat.day, *columns).where(
                    DailyStat.chat_id.in_(chat_ids), DailyStat.day >= prev_from,
                )
            )
        ).all()

        hourly = dict(
            (
                await session.execute(
                    select(HourlyStat.hour, func.sum(HourlyStat.messages))
                    .where(HourlyStat.chat_id.in_(chat_ids), HourlyStat.day >= day_from)
                    .group_by(HourlyStat.hour)
                )
            ).all()
        )

        returning = (
            await session.execute(
                select(func.count(func.distinct(GroupMember.telegram_id))).where(
                    GroupMember.chat_id.in_(chat_ids),
                    GroupMember.updated_at >= start,
                    GroupMember.joined_at < start,
                )
            )
        ).scalar() or 0

    current = dict.fromkeys(DAILY_FIELDS, 0)
    previous = dict.fromkeys(DAILY_FIELDS, 0)
    by_day: dict[str, dict] = {}

    for row in rows:
        day = row[0]
        values = dict(zip(DAILY_FIELDS, (int(v or 0) for v in row[1:])))
        target = current if day >= day_from else previous

        for key, value in values.items():
            target[key] += value

        if day >= day_from:
            slot = by_day.setdefault(day, dict.fromkeys(DAILY_FIELDS, 0))
            for key, value in values.items():
                slot[key] += value

    series = []

    for offset in range(days):
        day = (now - timedelta(days=days - 1 - offset)).strftime("%Y-%m-%d")
        series.append({"day": day, **by_day.get(day, dict.fromkeys(DAILY_FIELDS, 0))})

    return {
        "current": current,
        "previous": previous,
        "change": {key: compare(current[key], previous[key]) for key in DAILY_FIELDS},
        "series": series,
        # Часы хранятся по UTC — сдвигаем в часовой пояс группы
        "hours": [int(hourly.get((h - offset) % 24, 0) or 0) for h in range(24)],
        "returning": int(returning),
        "economy": await economy_flow(chat_ids, days=days),
    }



async def audit_actors(chat_ids: list[int] | None, limit: int = 30) -> list[dict]:
    """Кто из админов что-то делал — для фильтра журнала."""
    async with session_scope() as session:
        stmt = (
            select(AuditEvent.actor_id, func.max(AuditEvent.actor_name), func.count(AuditEvent.id))
            .where(AuditEvent.actor_kind == "admin", AuditEvent.actor_id.is_not(None))
            .group_by(AuditEvent.actor_id)
            .order_by(desc(func.count(AuditEvent.id)))
            .limit(limit)
        )

        if chat_ids is not None:
            stmt = stmt.where(AuditEvent.chat_id.in_(chat_ids) | AuditEvent.chat_id.is_(None))

        rows = (await session.execute(stmt)).all()

    return [{"id": uid, "name": name or str(uid), "count": int(n)} for uid, name, n in rows]



async def replace_action_custom_image(chat_id: int, custom_id: int, value: str) -> bool:
    """Заменить свою картинку: новое содержимое, file_id и счётчик — заново."""
    async with session_scope() as session:
        result = await session.execute(
            update(ActionCustom)
            .where(
                ActionCustom.id == custom_id,
                ActionCustom.chat_id == chat_id,
                ActionCustom.kind == "image",
            )
            .values(value=value, file_id=None, shows=0, last_used_at=None)
        )
        await session.commit()
        return (result.rowcount or 0) > 0



async def clear_builtin_hide(chat_id: int, action_key: str, kind: str, value: str) -> None:
    """
    Снять отметку «скрыто» со встроенного слова или фразы.
    Фраза общая для категории, поэтому её отметка — на всю группу.
    """
    async with session_scope() as session:
        stmt = ActionCustom.__table__.delete().where(
            ActionCustom.chat_id == chat_id,
            ActionCustom.kind == kind,
            ActionCustom.value == value,
        )

        if kind == "hide_alias":
            stmt = stmt.where(ActionCustom.action_key == action_key)

        await session.execute(stmt)
        await session.commit()


# =========================================================
# СВОИ ПРАВИЛА НАКАЗАНИЙ
# =========================================================

MAX_RULES = 10


async def list_punish_rules(chat_id: int) -> list:
    async with session_scope() as session:
        return list(
            (await session.execute(
                select(PunishRule).where(PunishRule.chat_id == chat_id)
                .order_by(PunishRule.position, PunishRule.id)
            )).scalars().all()
        )


async def save_punish_rule(chat_id: int, data: dict, rule_id: int | None = None) -> int:
    async with session_scope() as session:
        if rule_id:
            item = (await session.execute(
                select(PunishRule).where(PunishRule.id == rule_id, PunishRule.chat_id == chat_id)
            )).scalar_one_or_none()

            if item is None:
                return 0
        else:
            count = (await session.execute(
                select(func.count(PunishRule.id)).where(PunishRule.chat_id == chat_id)
            )).scalar() or 0

            if count >= MAX_RULES:
                return -1

            item = PunishRule(chat_id=chat_id, position=count)
            session.add(item)

        for field in ("violation", "count", "window_minutes", "action", "duration_minutes", "enabled"):
            if field in data:
                setattr(item, field, data[field])

        await session.commit()
        return item.id


async def delete_punish_rule(chat_id: int, rule_id: int) -> bool:
    async with session_scope() as session:
        result = await session.execute(
            PunishRule.__table__.delete().where(PunishRule.id == rule_id, PunishRule.chat_id == chat_id)
        )
        await session.commit()
        return (result.rowcount or 0) > 0


async def move_punish_rule(chat_id: int, rule_id: int, direction: int) -> None:
    """Поднять или опустить правило: порядок важен, срабатывает первое."""
    rules = await list_punish_rules(chat_id)
    ids = [r.id for r in rules]

    if rule_id not in ids:
        return

    i = ids.index(rule_id)
    j = max(0, min(len(ids) - 1, i + direction))
    ids[i], ids[j] = ids[j], ids[i]

    async with session_scope() as session:
        for position, rid in enumerate(ids):
            await session.execute(update(PunishRule).where(PunishRule.id == rid).values(position=position))
        await session.commit()


# =========================================================
# ЛИЧНЫЕ РАССЫЛКИ
# =========================================================

async def mark_dm_ok(telegram_id: int, ok: bool) -> None:
    async with session_scope() as session:
        await session.execute(update(User).where(User.telegram_id == telegram_id).values(dm_ok=ok))
        await session.commit()


SEGMENTS = ("all", "active", "vip", "level", "balance", "achievement")


async def dm_audience(chat_ids: list[int], segment: dict) -> list[int]:
    """
    Кому можно написать в личку: человек сам запускал бота и состоит
    в группах админа. Дальше — фильтр сегмента.
    """
    kind = segment.get("type") if segment.get("type") in SEGMENTS else "all"
    value = segment.get("value")

    async with session_scope() as session:
        stmt = (
            select(User.telegram_id)
            .join(GroupMember, GroupMember.telegram_id == User.telegram_id)
            .where(User.dm_ok.is_(True), GroupMember.chat_id.in_(chat_ids), GroupMember.left_at.is_(None))
        )

        if kind == "active":
            stmt = stmt.where(GroupMember.updated_at >= utcnow() - timedelta(days=7))
        elif kind == "vip":
            stmt = stmt.where(GroupMember.vip.is_(True))
        elif kind in ("level", "balance"):
            column = UserProfile.level if kind == "level" else UserProfile.coins
            stmt = stmt.join(UserProfile, UserProfile.telegram_id == User.telegram_id).where(
                column >= int(value or 0)
            )
        elif kind == "achievement":
            stmt = stmt.join(UserAchievement, UserAchievement.telegram_id == User.telegram_id).where(
                UserAchievement.achievement_key == str(value or "")
            )

        return sorted(set((await session.execute(stmt)).scalars().all()))


# =========================================================
# СВОЯ КОЛЛЕКЦИЯ КАРТИНОК
# =========================================================

async def add_library_images(tag: str, photos: list[tuple[str, str]], author_id: int | None) -> tuple[int, int]:
    """Добавляет фото в коллекцию. Возвращает (добавлено, уже были)."""
    added = duplicates = 0

    async with session_scope() as session:
        known = set(
            (await session.execute(
                select(LibraryImage.file_unique_id).where(LibraryImage.tag == tag)
            )).scalars().all()
        )

        for file_id, unique_id in photos:
            if unique_id in known:
                duplicates += 1
                continue

            known.add(unique_id)
            session.add(LibraryImage(tag=tag, file_id=file_id, file_unique_id=unique_id, author_id=author_id))
            added += 1

        await session.commit()

    return added, duplicates


async def library_summary() -> list[dict]:
    async with session_scope() as session:
        rows = (await session.execute(
            select(LibraryImage.tag, func.count(LibraryImage.id), func.coalesce(func.sum(LibraryImage.shows), 0),
                   func.max(LibraryImage.created_at))
            .group_by(LibraryImage.tag).order_by(LibraryImage.tag)
        )).all()

        links = (await session.execute(select(LibraryLink.tag, LibraryLink.target))).all()

    targets: dict[str, list] = {}

    for tag, target in links:
        targets.setdefault(tag, []).append(target)

    return [
        {"tag": tag, "count": int(n), "shows": int(shows), "updated": last.isoformat() if last else None,
         "targets": sorted(targets.get(tag, []))}
        for tag, n, shows, last in rows
    ]


async def library_images(tag: str, limit: int = 60, offset: int = 0) -> list[dict]:
    async with session_scope() as session:
        rows = (await session.execute(
            select(LibraryImage).where(LibraryImage.tag == tag)
            .order_by(LibraryImage.created_at.desc(), LibraryImage.id.desc())
            .offset(offset).limit(limit)
        )).scalars().all()

    return [
        {"id": r.id, "shows": r.shows, "used": r.used,
         "last_used": r.last_used_at.isoformat() if r.last_used_at else None}
        for r in rows
    ]


async def library_image(image_id: int):
    async with session_scope() as session:
        return (await session.execute(select(LibraryImage).where(LibraryImage.id == image_id))).scalar_one_or_none()


async def delete_library_image(image_id: int) -> bool:
    async with session_scope() as session:
        result = await session.execute(LibraryImage.__table__.delete().where(LibraryImage.id == image_id))
        await session.commit()
        return (result.rowcount or 0) > 0


async def delete_library_collection(tag: str) -> int:
    async with session_scope() as session:
        result = await session.execute(LibraryImage.__table__.delete().where(LibraryImage.tag == tag))
        await session.execute(LibraryLink.__table__.delete().where(LibraryLink.tag == tag))
        await session.execute(LibraryCollection.__table__.delete().where(LibraryCollection.tag == tag))
        await session.commit()
        return result.rowcount or 0


async def all_library_links() -> list[tuple[str, str]]:
    async with session_scope() as session:
        return [(t, g) for t, g in (await session.execute(select(LibraryLink.tag, LibraryLink.target))).all()]


async def set_library_link(tag: str, target: str, linked: bool) -> None:
    async with session_scope() as session:
        await session.execute(
            LibraryLink.__table__.delete().where(LibraryLink.tag == tag, LibraryLink.target == target)
        )

        if linked:
            session.add(LibraryLink(tag=tag, target=target))

        await session.commit()


async def pick_library_image(tags: list[str]):
    """
    Картинка из коллекций по кругу: сначала непоказанные; когда
    показаны все — круг начинается заново.
    """
    if not tags:
        return None

    async with session_scope() as session:
        fresh = (await session.execute(
            select(LibraryImage).where(LibraryImage.tag.in_(tags), LibraryImage.used.is_(False))
            .order_by(func.random()).limit(1)
        )).scalar_one_or_none()

        if fresh is None:
            await session.execute(
                update(LibraryImage).where(LibraryImage.tag.in_(tags)).values(used=False)
            )

            fresh = (await session.execute(
                select(LibraryImage).where(LibraryImage.tag.in_(tags)).order_by(func.random()).limit(1)
            )).scalar_one_or_none()

        if fresh is None:
            await session.commit()
            return None

        fresh.used = True
        fresh.shows += 1
        fresh.last_used_at = utcnow()

        result = {"id": fresh.id, "file_id": fresh.file_id, "tag": fresh.tag}

        await session.commit()

    return result



async def list_library_collections() -> list:
    async with session_scope() as session:
        return list((await session.execute(select(LibraryCollection).order_by(LibraryCollection.tag))).scalars().all())


async def ensure_library_collection(tag: str, as_action: bool) -> bool:
    """Создаёт запись коллекции, если её ещё нет. True — создана сейчас."""
    async with session_scope() as session:
        exists = (await session.execute(
            select(LibraryCollection.id).where(LibraryCollection.tag == tag)
        )).scalar_one_or_none()

        if exists is not None:
            return False

        session.add(LibraryCollection(tag=tag, as_action=as_action, triggers=[]))
        await session.commit()
        return True


async def update_library_collection(tag: str, data: dict) -> bool:
    async with session_scope() as session:
        item = (await session.execute(
            select(LibraryCollection).where(LibraryCollection.tag == tag)
        )).scalar_one_or_none()

        if item is None:
            return False

        for field in ("emoji", "as_action", "triggers", "phrase"):
            if field in data:
                setattr(item, field, data[field])

        await session.commit()
        return True
