import re
from html import escape

from aiogram import Router
from aiogram.types import Message

from actions.catalog import find_action
from actions.service import get_image_for_action

from database.repository import (
    save_user,
    save_message,
    get_user_by_username,
)


router = Router()


def get_display_name(user) -> str:

    if user.first_name:
        return user.first_name

    if user.username:
        return user.username

    return "Пользователь"


def to_accusative(name: str) -> str:

    if not name:
        return name

    # Женские имена на -а
    if name.endswith("а"):
        return name[:-1] + "у"

    # Женские имена на -я
    if name.endswith("я"):
        return name[:-1] + "ю"

    # Мужские имена на -й
    if name.endswith("й"):
        return name[:-1] + "я"

    # Мужские имена на -ь
    if name.endswith("ь"):
        return name + "я"

    # Простые мужские имена
    # Стас -> Стаса
    # Иван -> Ивана
    # Андрей уже обработан выше
    return name + "а"


def to_instrumental(name: str) -> str:

    if not name:
        return name

    # Женские имена
    if name.endswith("а"):
        return name[:-1] + "ой"

    if name.endswith("я"):
        return name[:-1] + "ей"

    # Мужские имена
    if name.endswith("й"):
        return name[:-1] + "ем"

    if name.endswith("ь"):
        return name[:-1] + "ем"

    # Стас -> Стасом
    return name + "ом"


def contains_any(
    text: str,
    words: tuple[str, ...],
) -> bool:

    normalized = text.lower()

    return any(
        word in normalized
        for word in words
    )


def build_action_text(
    message_text: str,
    actor_name: str,
    target_name: str,
    action,
) -> str:

    text = message_text.lower()

    actor = escape(actor_name)

    target_acc = escape(
        to_accusative(target_name)
    )

    target_instr = escape(
        to_instrumental(target_name)
    )

    if contains_any(
        text,
        (
            "угост",
            "угощ",
        ),
    ):

        return (
            f"{action.emoji} "
            f"<b>{actor}</b> "
            f"угостил(а) "
            f"<b>{target_acc}</b> "
            f"{action.item_instr} ♡"
        )

    if contains_any(
        text,
        (
            "подар",
            "дарю",
        ),
    ):

        return (
            f"{action.emoji} "
            f"<b>{actor}</b> "
            f"подарил(а) "
            f"<b>{target_acc}</b> "
            f"{action.item_acc} ♡"
        )

    if contains_any(
        text,
        (
            "обня",
            "обним",
        ),
    ):

        return (
            f"{action.emoji} "
            f"<b>{actor}</b> "
            f"обнял(а) "
            f"<b>{target_acc}</b> 🤗"
        )

    if contains_any(
        text,
        (
            "поцелу",
            "целу",
        ),
    ):

        return (
            f"{action.emoji} "
            f"<b>{actor}</b> "
            f"поцеловал(а) "
            f"<b>{target_acc}</b> 😘"
        )

    if contains_any(
        text,
        (
            "поддерж",
        ),
    ):

        return (
            f"{action.emoji} "
            f"<b>{actor}</b> "
            f"поддержал(а) "
            f"<b>{target_acc}</b> 🫶"
        )

    if contains_any(
        text,
        (
            "поздрав",
        ),
    ):

        return (
            f"{action.emoji} "
            f"<b>{actor}</b> "
            f"поздравил(а) "
            f"<b>{target_acc}</b> 🎉"
        )

    if contains_any(
        text,
        (
            "танц",
        ),
    ):

        return (
            f"{action.emoji} "
            f"<b>{actor}</b> "
            f"потанцевал(а) "
            f"с <b>{target_instr}</b> 💃"
        )

    # Стандартный вариант:
    # Пиво -> выпил(а) пиво вместе с Еленой
    return (
        f"{action.emoji} "
        f"<b>{actor}</b> "
        f"выпил(а) "
        f"{action.item_acc} "
        f"вместе с <b>{target_instr}</b> ♡"
    )


async def find_target(
    message: Message,
):

    # -----------------------------------------------------
    # ВАРИАНТ 1 — ОТВЕТ НА СООБЩЕНИЕ
    # -----------------------------------------------------

    if message.reply_to_message:

        target = message.reply_to_message.from_user

        if target is not None:

            if target.is_bot:
                return None

            return target

    # -----------------------------------------------------
    # ВАРИАНТ 2 — @username
    # -----------------------------------------------------

    text = message.text or ""

    match = re.search(
        r"@([A-Za-z0-9_]{3,32})",
        text,
    )

    if match:

        username = match.group(1)

        user = await get_user_by_username(
            username
        )

        if user is not None:
            return user

    return None


@router.message()
async def action_handler(
    message: Message,
):

    # Только группы
    if message.chat.type not in (
        "group",
        "supergroup",
    ):
        return

    if not message.from_user:
        return

    if message.from_user.is_bot:
        return

    text = message.text

    if not text:
        return

    # Ищем действие
    action = find_action(text)

    if action is None:
        return

    # Действие должно быть адресовано человеку:
    # ответом на сообщение или через @username.
    target = await find_target(
        message
    )

    if target is None:
        return

    if target.id == message.from_user.id:
        return

    # Сохраняем пользователей
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

    # Сохраняем само действие в историю
    await save_message(
        chat_id=message.chat.id,
        telegram_user_id=message.from_user.id,
        username=message.from_user.first_name
        or message.from_user.username,
        message=text,
    )

    try:

        image = await get_image_for_action(
            action
        )

    except Exception as error:

        print(
            "ACTION IMAGE ERROR:",
            type(error).__name__,
            str(error),
        )

        await message.reply(
            "Не смогла найти картинку 😔"
        )

        return

    if image is None:

        await message.reply(
            "Для этого действия пока нет картинки 😔"
        )

        return

    actor_name = (
        message.from_user.first_name
        or message.from_user.username
        or "Пользователь"
    )

    target_name = (
        target.first_name
        or target.username
        or "Пользователь"
    )

    action_text = build_action_text(
        text,
        actor_name,
        target_name,
        action,
    )

    # Обязательная атрибуция Unsplash.
    attribution = (
        "\n\n"
        f"📷 <a href=\"{escape(image.photographer_url)}\">"
        f"Фото: {escape(image.photographer_name)}"
        f"</a> · "
        f"<a href=\"{escape(image.unsplash_url)}\">"
        f"Unsplash"
        f"</a>"
    )

    caption = (
        action_text
        + attribution
    )

    try:

        await message.bot.send_photo(
            chat_id=message.chat.id,
            photo=image.image_url,
            caption=caption,
            parse_mode="HTML",
        )

    except Exception as error:

        print(
            "TELEGRAM PHOTO ERROR:",
            type(error).__name__,
            str(error),
        )

        # Если Telegram не смог получить фото,
        # возвращаем его в доступные.
        from database.repository import (
            release_action_image
        )

        await release_action_image(
            image.id
        )

        await message.reply(
            "Не получилось отправить фотографию 😔"
        )
