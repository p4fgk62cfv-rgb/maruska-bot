import re
import random
from html import escape

from aiogram import Router
from aiogram.types import Message

from actions.catalog import find_action
from actions.service import get_image_for_action

from database.repository import (
    save_user,
    save_message,
    get_user_by_username,
    get_user_by_telegram_id,
    infer_gender,
)


router = Router()


# ---------------------------------------------------------
# Имена / род
# ---------------------------------------------------------

def get_display_name(user) -> str:
    if user.first_name:
        return user.first_name
    if user.username:
        return user.username
    return "Пользователь"


def get_gender_from_telegram_user(user) -> str:
    return infer_gender(get_display_name(user))


def get_gender_from_db_user(user) -> str:
    if user is None:
        return "unknown"
    if getattr(user, "gender", None):
        return user.gender
    return infer_gender(
        user.first_name or user.username or ""
    )


def pair_key(actor_gender: str, target_gender: str) -> str:
    if actor_gender == "male" and target_gender == "female":
        return "male_female"
    if actor_gender == "female" and target_gender == "male":
        return "male_female"
    if actor_gender == "male" and target_gender == "male":
        return "male_male"
    if actor_gender == "female" and target_gender == "female":
        return "female_female"
    return "neutral"


def contains_any(text: str, words: tuple[str, ...]) -> bool:
    normalized = text.lower()
    return any(word in normalized for word in words)


# ---------------------------------------------------------
# Русское склонение имён.
# Не пытаемся сделать идеальный морфологический движок —
# сначала используем известные окончания и список исключений.
# ---------------------------------------------------------

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
    "олег", "игорь", "василий", "юрии", "юрий", "богдан", "ярослав",
    "матвей", "тимур", "глеб", "лев", "марк", "петр", "пётр",
    "саша", "женя", "валера", "миша", "дима", "серёжа", "сережа",
    "лёша", "леша", "паша", "вова",
}


def to_accusative(name: str, gender: str = "unknown") -> str:
    if not name:
        return name

    clean = name.strip()
    lower = clean.lower()

    # Не склоняем usernames/имена из латиницы.
    if not re.search(r"[а-яё]", lower):
        return clean

    if gender == "female":
        if lower.endswith("ия"):
            return clean[:-2] + "ию"
        if lower.endswith("я"):
            return clean[:-1] + "ю"
        if lower.endswith("а"):
            return clean[:-1] + "у"
        if lower.endswith("ь"):
            return clean
        return clean

    if gender == "male":
        if lower.endswith("й"):
            return clean[:-1] + "я"
        if lower.endswith("я"):
            return clean[:-1] + "ю"
        if lower.endswith("ь"):
            return clean[:-1] + "я"
        if lower.endswith("а"):
            # Никита / Илья / Лука — редкое исключение для нашего списка.
            if lower in MALE_NAMES:
                if lower.endswith("я"):
                    return clean[:-1] + "ю"
                return clean[:-1] + "у"
        return clean + "а"

    # Если род неизвестен — не ломаем имя.
    return clean


def to_dative(name: str, gender: str = "unknown") -> str:
    if not name:
        return name

    clean = name.strip()
    lower = clean.lower()

    if not re.search(r"[а-яё]", lower):
        return clean

    if gender == "female":
        if lower.endswith("ия"):
            return clean[:-2] + "ии"
        if lower.endswith("я"):
            return clean[:-1] + "е"
        if lower.endswith("а"):
            return clean[:-1] + "е"
        if lower.endswith("ь"):
            return clean + "и"
        return clean

    if gender == "male":
        if lower.endswith("й"):
            return clean[:-1] + "ю"
        if lower.endswith("ь"):
            return clean[:-1] + "ю"
        if lower.endswith("я"):
            return clean[:-1] + "е"
        if lower.endswith("а") and lower in MALE_NAMES:
            return clean[:-1] + "е"
        return clean + "у"

    return clean


def to_instrumental(name: str, gender: str = "unknown") -> str:
    if not name:
        return name

    clean = name.strip()
    lower = clean.lower()

    if not re.search(r"[а-яё]", lower):
        return clean

    if gender == "female":
        if lower.endswith("ия"):
            return clean[:-2] + "ией"
        if lower.endswith("я"):
            return clean[:-1] + "ей"
        if lower.endswith("а"):
            return clean[:-1] + "ой"
        if lower.endswith("ь"):
            return clean + "ю"
        return clean

    if gender == "male":
        if lower.endswith("й"):
            return clean[:-1] + "ем"
        if lower.endswith("я"):
            return clean[:-1] + "ёй"
        if lower.endswith("ь"):
            return clean[:-1] + "ем"
        if lower.endswith("а") and lower in MALE_NAMES:
            return clean[:-1] + "ой"
        return clean + "ом"

    return clean


def _drink_verb(message_text: str) -> str:
    text = message_text.lower()

    if contains_any(text, ("угости", "угост", "угощ")):
        return "treat"

    if contains_any(text, ("напои", "напо", "поить", "пою")):
        return "pour"

    if contains_any(
        text,
        ("выпей", "выпить", "выпил", "выпила", "выпьем", "пью", "пить"),
    ):
        return "together"

    return random.choice(("treat", "pour", "together"))


def _food_verb(message_text: str) -> str:
    text = message_text.lower()

    if contains_any(text, ("накорм", "корми", "покорм")):
        return "feed"

    if contains_any(text, ("угости", "угост", "угощ")):
        return "treat"

    return random.choice(("treat", "feed"))


def build_action_text(
    message_text: str,
    actor_name: str,
    target_name: str,
    action,
    actor_gender: str = "unknown",
    target_gender: str = "unknown",
) -> str:
    actor = escape(actor_name)
    target_acc = escape(to_accusative(target_name, target_gender))
    target_dat = escape(to_dative(target_name, target_gender))
    target_instr = escape(to_instrumental(target_name, target_gender))

    if action.category == "drink":
        verb = _drink_verb(message_text)

        if verb == "treat":
            return (
                f"{action.emoji} <b>{actor}</b> "
                f"угостил(а) <b>{target_acc}</b> "
                f"{action.item_instr} ♡"
            )

        if verb == "pour":
            return (
                f"{action.emoji} <b>{actor}</b> "
                f"напоил(а) <b>{target_acc}</b> "
                f"{action.item_instr} ♡"
            )

        return (
            f"{action.emoji} <b>{actor}</b> "
            f"выпил(а) {action.item_acc} "
            f"вместе с <b>{target_instr}</b> ♡"
        )

    if action.category == "food":
        verb = _food_verb(message_text)
        if verb == "feed":
            return (
                f"{action.emoji} <b>{actor}</b> "
                f"накормил(а) <b>{target_acc}</b> "
                f"{action.item_instr} ♡"
            )
        return (
            f"{action.emoji} <b>{actor}</b> "
            f"угостил(а) <b>{target_acc}</b> "
            f"{action.item_instr} ♡"
        )

    if action.category == "flower":
        return (
            f"{action.emoji} <b>{actor}</b> "
            f"подарил(а) <b>{target_dat}</b> "
            f"{action.item_acc} ♡"
        )

    if action.category == "gift":
        return (
            f"{action.emoji} <b>{actor}</b> "
            f"подарил(а) <b>{target_dat}</b> "
            f"{action.item_acc} ♡"
        )

    if action.key == "hug":
        return f"🤗 <b>{actor}</b> обнял(а) <b>{target_acc}</b> 🤗"

    if action.key == "kiss":
        return f"😘 <b>{actor}</b> поцеловал(а) <b>{target_acc}</b> 😘"

    if action.key == "highfive":
        return f"🙌 <b>{actor}</b> дал(а) пять <b>{target_dat}</b> ✋"

    if action.key == "handshake":
        return f"🤝 <b>{actor}</b> пожал(а) руку <b>{target_acc}</b>"

    if action.key == "support":
        return f"🫶 <b>{actor}</b> поддержал(а) <b>{target_acc}</b>"

    if action.key == "congratulations":
        return f"🎉 <b>{actor}</b> поздравил(а) <b>{target_acc}</b> 🎉"

    if action.key == "party":
        return f"🎉 <b>{actor}</b> тусовался(ась) вместе с <b>{target_instr}</b>"

    if action.key == "movie":
        return f"🎬 <b>{actor}</b> посмотрел(а) кино вместе с <b>{target_instr}</b>"

    if action.key == "music":
        return f"🎵 <b>{actor}</b> послушал(а) музыку вместе с <b>{target_instr}</b>"

    if action.key == "dance":
        return f"💃 <b>{actor}</b> потанцевал(а) с <b>{target_instr}</b>"

    return f"{action.emoji} <b>{actor}</b> сделал(а) что-то вместе с <b>{target_instr}</b> ♡"


async def find_target(message: Message):
    if message.reply_to_message:
        target = message.reply_to_message.from_user
        if target is not None and not target.is_bot:
            return target

    text = message.text or ""
    match = re.search(r"@([A-Za-z0-9_]{3,32})", text)
    if match:
        return await get_user_by_username(match.group(1))

    return None


@router.message()
async def action_handler(message: Message):
    if message.chat.type not in ("group", "supergroup"):
        return
    if not message.from_user or message.from_user.is_bot:
        return
    if not message.text:
        return

    action = find_action(message.text)
    if action is None:
        return

    target = await find_target(message)
    if target is None or target.id == message.from_user.id:
        return

    await save_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    await save_user(
        telegram_id=target.id,
        username=target.username,
        first_name=target.first_name,
    )

    await save_message(
        chat_id=message.chat.id,
        telegram_user_id=message.from_user.id,
        username=message.from_user.first_name or message.from_user.username,
        message=message.text,
    )

    actor_gender = get_gender_from_telegram_user(message.from_user)

    if hasattr(target, "first_name"):
        target_gender = infer_gender(
            target.first_name or target.username or ""
        )
    else:
        target_gender = get_gender_from_db_user(target)

    image_key = action.key
    pair = "neutral"

    if action.category == "pair":
        pair = pair_key(actor_gender, target_gender)
        image_key = f"{action.key}:{pair}"

    try:
        image = await get_image_for_action(
            action,
            image_key=image_key,
            pair_key=pair,
        )
    except Exception as error:
        print(
            "ACTION IMAGE ERROR:",
            type(error).__name__,
            str(error),
        )
        await message.reply("Не смогла найти картинку 😔")
        return

    if image is None:
        await message.reply("Для этого действия пока нет картинки 😔")
        return

    actor_name = get_display_name(message.from_user)
    target_name = get_display_name(target)

    caption = build_action_text(
        message.text,
        actor_name,
        target_name,
        action,
        actor_gender=actor_gender,
        target_gender=target_gender,
    )

    # Unsplash пока оставляем как текущий источник,
    # поэтому обязательную API-атрибуцию не удаляем.
    attribution = (
        "\n\n"
        f"📷 <a href=\"{escape(image.photographer_url)}\">"
        f"Фото: {escape(image.photographer_name)}"
        f"</a> · "
        f"<a href=\"{escape(image.unsplash_url)}\">"
        f"Unsplash"
        f"</a>"
    )

    try:
        await message.bot.send_photo(
            chat_id=message.chat.id,
            photo=image.image_url,
            caption=caption + attribution,
            parse_mode="HTML",
        )
    except Exception as error:
        print(
            "TELEGRAM PHOTO ERROR:",
            type(error).__name__,
            str(error),
        )
        from database.repository import release_action_image
        await release_action_image(image.id)
        await message.reply("Не получилось отправить фотографию 😔")
