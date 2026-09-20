import random
import re
from dataclasses import dataclass
from html import escape

from aiogram import Router
from aiogram.types import BufferedInputFile, Message

from actions.catalog import find_action
from actions.providers import download_photo
from actions.service import get_image_for_action

from database.repository import (
    save_user,
    save_message,
    get_user_by_username,
    infer_gender,
    release_action_image,
    drop_action_image,
    set_action_image_file_id,
    MALE_NAMES,
)


router = Router(name="actions")

USERNAME_RE = re.compile(r"@([A-Za-z0-9_]{5,32})")

GROUP_CHATS = ("group", "supergroup")


@dataclass(frozen=True)
class Target:
    """
    Единый вид цели независимо от того, откуда она взялась:
    из reply (aiogram User) или из базы (ORM User).

    Старый баг: из базы возвращался ORM-объект, у которого .id —
    это автоинкремент строки, а не Telegram ID. В результате
    в users создавались фейковые пользователи с telegram_id = 3, 7, 12.
    """
    telegram_id: int
    username: str | None
    first_name: str | None


# ---------------------------------------------------------
# Имена / род
# ---------------------------------------------------------

def get_display_name(user) -> str:
    if getattr(user, "first_name", None):
        return user.first_name
    if getattr(user, "username", None):
        return user.username
    return "Пользователь"


def pair_key(actor_gender: str, target_gender: str) -> str:
    if {actor_gender, target_gender} == {"male", "female"}:
        return "male_female"
    if actor_gender == target_gender == "male":
        return "male_male"
    if actor_gender == target_gender == "female":
        return "female_female"
    return "neutral"


def contains_any(text: str, words: tuple[str, ...]) -> bool:
    normalized = text.lower()
    return any(word in normalized for word in words)


def vform(male: str, female: str, gender: str) -> str:
    """
    Форма глагола по роду. Если род неизвестен — старый вариант "(а)".
    """
    if gender == "male":
        return male
    if gender == "female":
        return female
    if female.startswith(male):
        return f"{male}({female[len(male):]})"
    return f"{male}/{female}"


# ---------------------------------------------------------
# Русское склонение имён.
# Не морфологический движок — окончания + список исключений.
# ---------------------------------------------------------

def _is_cyrillic(value: str) -> bool:
    return bool(re.search(r"[а-яё]", value))


def to_accusative(name: str, gender: str = "unknown") -> str:
    if not name:
        return name

    clean = name.strip()
    lower = clean.lower()

    # Латиницу и никнеймы не склоняем.
    if not _is_cyrillic(lower):
        return clean

    if gender == "female":
        if lower.endswith("ия"):
            return clean[:-2] + "ию"
        if lower.endswith("я"):
            return clean[:-1] + "ю"
        if lower.endswith("а"):
            return clean[:-1] + "у"
        return clean

    if gender == "male":
        if lower.endswith("й"):
            return clean[:-1] + "я"
        if lower.endswith("я"):
            return clean[:-1] + "ю"
        if lower.endswith("ь"):
            return clean[:-1] + "я"
        if lower.endswith("а"):
            if lower in MALE_NAMES:
                return clean[:-1] + "у"
            return clean
        return clean + "а"

    return clean


def to_dative(name: str, gender: str = "unknown") -> str:
    if not name:
        return name

    clean = name.strip()
    lower = clean.lower()

    if not _is_cyrillic(lower):
        return clean

    if gender == "female":
        if lower.endswith("ия"):
            return clean[:-2] + "ии"
        if lower.endswith(("я", "а")):
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
        if lower.endswith("а"):
            if lower in MALE_NAMES:
                return clean[:-1] + "е"
            return clean
        return clean + "у"

    return clean


def to_instrumental(name: str, gender: str = "unknown") -> str:
    if not name:
        return name

    clean = name.strip()
    lower = clean.lower()

    if not _is_cyrillic(lower):
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
            return clean[:-1] + "ей"
        if lower.endswith("ь"):
            return clean[:-1] + "ем"
        if lower.endswith("а"):
            if lower in MALE_NAMES:
                return clean[:-1] + "ой"
            return clean
        return clean + "ом"

    return clean


# ---------------------------------------------------------
# Текст действия
# ---------------------------------------------------------

def _drink_verb(message_text: str) -> str:
    text = message_text.lower()

    if contains_any(text, ("угост", "угощ")):
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

    if contains_any(text, ("угост", "угощ")):
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

    g = actor_gender

    if action.category == "drink":
        verb = _drink_verb(message_text)

        if verb == "treat":
            word = vform("угостил", "угостила", g)
            return (
                f"{action.emoji} <b>{actor}</b> {word} "
                f"<b>{target_acc}</b> {action.item_instr} ♡"
            )

        if verb == "pour":
            word = vform("напоил", "напоила", g)
            return (
                f"{action.emoji} <b>{actor}</b> {word} "
                f"<b>{target_acc}</b> {action.item_instr} ♡"
            )

        word = vform("выпил", "выпила", g)
        return (
            f"{action.emoji} <b>{actor}</b> {word} {action.item_acc} "
            f"вместе с <b>{target_instr}</b> ♡"
        )

    if action.category == "food":
        verb = _food_verb(message_text)

        if verb == "feed":
            word = vform("накормил", "накормила", g)
        else:
            word = vform("угостил", "угостила", g)

        return (
            f"{action.emoji} <b>{actor}</b> {word} "
            f"<b>{target_acc}</b> {action.item_instr} ♡"
        )

    if action.category in ("flower", "gift"):
        word = vform("подарил", "подарила", g)
        return (
            f"{action.emoji} <b>{actor}</b> {word} "
            f"<b>{target_dat}</b> {action.item_acc} ♡"
        )

    if action.key == "hug":
        word = vform("обнял", "обняла", g)
        return f"🤗 <b>{actor}</b> {word} <b>{target_acc}</b> 🤗"

    if action.key == "kiss":
        word = vform("поцеловал", "поцеловала", g)
        return f"😘 <b>{actor}</b> {word} <b>{target_acc}</b> 😘"

    if action.key == "highfive":
        word = vform("дал", "дала", g)
        return f"🙌 <b>{actor}</b> {word} пять <b>{target_dat}</b> ✋"

    if action.key == "handshake":
        word = vform("пожал", "пожала", g)
        return f"🤝 <b>{actor}</b> {word} руку <b>{target_dat}</b>"

    if action.key == "support":
        word = vform("поддержал", "поддержала", g)
        return f"🫶 <b>{actor}</b> {word} <b>{target_acc}</b>"

    if action.key == "congratulations":
        word = vform("поздравил", "поздравила", g)
        return f"🎉 <b>{actor}</b> {word} <b>{target_acc}</b> 🎉"

    if action.key == "party":
        word = vform("оторвался", "оторвалась", g)
        return f"🎉 <b>{actor}</b> {word} вместе с <b>{target_instr}</b>"

    if action.key == "movie":
        word = vform("посмотрел", "посмотрела", g)
        return f"🎬 <b>{actor}</b> {word} кино вместе с <b>{target_instr}</b>"

    if action.key == "music":
        word = vform("послушал", "послушала", g)
        return f"🎵 <b>{actor}</b> {word} музыку вместе с <b>{target_instr}</b>"

    if action.key == "dance":
        word = vform("потанцевал", "потанцевала", g)
        return f"💃 <b>{actor}</b> {word} с <b>{target_instr}</b>"

    word = vform("провёл", "провела", g)
    return (
        f"{action.emoji} <b>{actor}</b> {word} время "
        f"вместе с <b>{target_instr}</b> ♡"
    )


# ---------------------------------------------------------
# Фильтр
# ---------------------------------------------------------

def is_action_message(message: Message) -> bool:
    """
    Синхронный фильтр. Действие засчитывается только если:
      - это групповой чат,
      - текст распознан как короткое действие,
      - есть адресат (reply на живого человека или @username).

    Всё остальное уходит дальше — в команды и в AI-хендлер.
    """
    if message.chat.type not in GROUP_CHATS:
        return False

    if not message.from_user or message.from_user.is_bot:
        return False

    if not message.text:
        return False

    if find_action(message.text) is None:
        return False

    reply = message.reply_to_message

    if reply and reply.from_user and not reply.from_user.is_bot:
        if reply.from_user.id != message.from_user.id:
            return True

    return bool(USERNAME_RE.search(message.text))


async def find_target(message: Message) -> Target | None:
    reply = message.reply_to_message

    if reply and reply.from_user and not reply.from_user.is_bot:
        user = reply.from_user
        return Target(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
        )

    match = USERNAME_RE.search(message.text or "")

    if match:
        db_user = await get_user_by_username(match.group(1))
        if db_user is not None:
            return Target(
                telegram_id=db_user.telegram_id,
                username=db_user.username,
                first_name=db_user.first_name,
            )

    return None


# ---------------------------------------------------------
# Хендлер
# ---------------------------------------------------------

@router.message(is_action_message)
async def action_handler(message: Message):
    action = find_action(message.text)
    if action is None:
        return

    target = await find_target(message)

    if target is None or target.telegram_id == message.from_user.id:
        return

    await save_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    await save_user(
        telegram_id=target.telegram_id,
        username=target.username,
        first_name=target.first_name,
    )

    await save_message(
        chat_id=message.chat.id,
        telegram_user_id=message.from_user.id,
        username=message.from_user.first_name or message.from_user.username,
        message=message.text,
    )

    actor_name = get_display_name(message.from_user)
    target_name = get_display_name(target)

    actor_gender = infer_gender(actor_name)
    target_gender = infer_gender(target_name)

    pair = "neutral"

    if action.category == "pair":
        pair = pair_key(actor_gender, target_gender)

    try:
        image = await get_image_for_action(action, pair_key=pair)
    except Exception as error:
        print("ACTION IMAGE ERROR:", type(error).__name__, str(error))
        await message.reply("Не смогла найти картинку 😔")
        return

    if image is None:
        await message.reply("Для этого действия пока нет картинки 😔")
        return

    caption = build_action_text(
        message.text,
        actor_name,
        target_name,
        action,
        actor_gender=actor_gender,
        target_gender=target_gender,
    )

    # Подпись только там, где лицензия источника её требует.
    # Pixabay атрибуции не требует — под фото ничего не пишем.
    if image.provider == "unsplash" and image.photographer_url:
        caption += (
            "\n\n"
            f'📷 <a href="{escape(image.photographer_url)}">'
            f"Фото: {escape(image.photographer_name or 'Unsplash')}</a> · "
            f'<a href="{escape(image.unsplash_url or "")}">Unsplash</a>'
        )

    sent = None

    # 1. Уже отправляли раньше — шлём по file_id, это мгновенно.
    if image.telegram_file_id:
        try:
            sent = await message.answer_photo(
                photo=image.telegram_file_id,
                caption=caption,
            )
        except Exception as error:
            print("FILE ID SEND ERROR:", type(error).__name__, str(error))

    # 2. Первый раз — скачиваем и заливаем байтами.
    #    Pixabay запрещает постоянный хотлинк своих URL.
    if sent is None:
        content = await download_photo(image.image_url, image.fallback_url)

        if content is None:
            await drop_action_image(image.id)
            await message.reply("Не получилось загрузить фотографию 😔")
            return

        try:
            sent = await message.answer_photo(
                photo=BufferedInputFile(
                    content,
                    filename=f"{action.key}.jpg",
                ),
                caption=caption,
            )
        except Exception as error:
            print("TELEGRAM PHOTO ERROR:", type(error).__name__, str(error))
            await release_action_image(image.id)
            await message.reply("Не получилось отправить фотографию 😔")
            return

    # Запоминаем file_id: больше к источнику не ходим.
    if not image.telegram_file_id and sent.photo:
        try:
            await set_action_image_file_id(image.id, sent.photo[-1].file_id)
        except Exception as error:
            print("FILE ID CACHE ERROR:", type(error).__name__, str(error))
