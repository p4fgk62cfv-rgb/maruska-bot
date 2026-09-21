from datetime import timedelta

from sqlalchemy import (
    select,
    desc,
    func,
    update,
)

from database.database import session_scope, utcnow

from database.models import (
    DrawingLike,
    GameRound,
    InventoryItem,
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
):
    async with session_scope() as session:

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
                )
            )
        else:
            if username:
                member.display_name = username
            member.messages_count += 1
            member.updated_at = utcnow()

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
) -> bool:
    async with session_scope() as session:
        cooldown_time = utcnow() - timedelta(hours=RATING_COOLDOWN_HOURS)

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
