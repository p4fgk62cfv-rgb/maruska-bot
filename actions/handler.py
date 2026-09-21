import re
from dataclasses import dataclass
from html import escape

from aiogram import Router
from aiogram.types import BufferedInputFile, Message

from actions.catalog import find_action
from settings.store import is_enabled
from actions.phrases import pick_template, render
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


# ---------------------------------------------------------
# Русское склонение имён.
# Не морфологический движок — окончания + список исключений.
# ---------------------------------------------------------

_NAME_RE = re.compile(r"^[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)?$")


def _is_declinable(name: str) -> bool:
    """
    Склоняем только то, что похоже на имя: одно кириллическое слово.

    Ники вроде "Унесенный Ветром", "Panda 🐼" или "DJ Vova" оставляем
    как есть — иначе получается "Унесенный Ветрому".
    """
    clean = name.strip()

    if len(clean) < 3:
        return False

    return bool(_NAME_RE.match(clean))


def to_accusative(name: str, gender: str = "unknown") -> str:
    if not name:
        return name

    clean = name.strip()
    lower = clean.lower()

    if not _is_declinable(clean):
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

    if not _is_declinable(clean):
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

    if not _is_declinable(clean):
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


def to_genitive(name: str, gender: str = "unknown") -> str:
    if not name:
        return name

    clean = name.strip()
    lower = clean.lower()

    if not _is_declinable(clean):
        return clean

    if gender == "female":
        if lower.endswith("ия"):
            return clean[:-2] + "ии"
        if lower.endswith("я"):
            return clean[:-1] + "и"
        if lower.endswith("а"):
            # после г, к, х, ж, ч, ш, щ пишется "и": Ольга -> Ольги
            if len(lower) > 1 and lower[-2] in "гкхжчшщ":
                return clean[:-1] + "и"
            return clean[:-1] + "ы"
        if lower.endswith("ь"):
            return clean[:-1] + "и"
        return clean

    if gender == "male":
        if lower.endswith("й"):
            return clean[:-1] + "я"
        if lower.endswith("ь"):
            return clean[:-1] + "я"
        if lower.endswith("я"):
            return clean[:-1] + "и"
        if lower.endswith("а"):
            if lower in MALE_NAMES:
                return clean[:-1] + "ы"
            return clean
        return clean + "а"

    return clean

# ---------------------------------------------------------
# Текст действия
# ---------------------------------------------------------

def build_action_text(
    message_text: str,
    actor_name: str,
    target_name: str,
    action,
    actor_gender: str = "unknown",
    target_gender: str = "unknown",
) -> str:
    template = pick_template(action)

    return render(
        template,
        actor_gender,
        emoji=action.emoji,
        actor=escape(actor_name),
        actor_gen=escape(to_genitive(actor_name, actor_gender)),
        actor_dat=escape(to_dative(actor_name, actor_gender)),
        target=escape(target_name),
        target_acc=escape(to_accusative(target_name, target_gender)),
        target_dat=escape(to_dative(target_name, target_gender)),
        target_gen=escape(to_genitive(target_name, target_gender)),
        target_instr=escape(to_instrumental(target_name, target_gender)),
        item=escape(action.item_acc),
        item_instr=escape(action.item_instr),
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

    if not is_enabled(message.chat.id, "actions"):
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
