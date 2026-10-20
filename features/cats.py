"""
Котики: «покажи меня» и «мяу».
"""

import asyncio
import logging
import random
import time
from html import escape

from aiogram import Router
from aiogram.types import Message

from actions.handler import send_picked
from actions.service import get_image_for_action
from actions.show_me import (
    is_meow,
    is_show_me,
    is_show_other,
    MONKEY_STEMS,
    pick_caption,
    pick_meow_caption,
    pick_mood,
)

from botcontext import display_name_of, is_addressed

from settings.store import is_enabled

logger = logging.getLogger("maruska.cats")

router = Router(name="cats")


# Пара котиков наготове: поиск в Pixabay, скачивание и загрузка занимают
# несколько секунд, а заранее подобранный котик уходит почти сразу
READY_SIZE = 2
_ready: list = []
_refilling = False


async def _fetch_cat():
    try:
        return await get_image_for_action(pick_mood())
    except Exception as error:
        logger.error("CAT: %s %s", type(error).__name__, error)
        return None


async def _refill() -> None:
    global _refilling
    if _refilling:
        return
    _refilling = True
    try:
        while len(_ready) < READY_SIZE:
            picked = await _fetch_cat()
            if picked is None:
                break
            _ready.append(picked)
    finally:
        _refilling = False


async def send_cat(message: Message, caption: str):
    try:
        await message.bot.send_chat_action(message.chat.id, "upload_photo")
    except Exception:
        pass

    # Сначала котики из своей коллекции
    import images_library

    library = await images_library.pick(message.chat.id, images_library.CATS)

    if library is not None:
        try:
            await message.answer_photo(photo=library["file_id"], caption=caption)
            return
        except Exception as error:
            logger.error("LIBRARY CAT: %s %s", type(error).__name__, error)

    picked = _ready.pop(0) if _ready else await _fetch_cat()

    # Следующих котиков готовим в фоне, пока этот отправляется
    asyncio.create_task(_refill())

    if picked is None:
        await message.reply("Котики закончились, попробуй попозже 🐾")
        return

    sent = await send_picked(message, picked, caption, "cat")

    if sent is None:
        await message.reply("Котик не отправился 🐾")


# Каждый второй портрет — обезьянка, если есть своя коллекция #обезьяна
MONKEY_CHANCE = 0.5
MONKEY_TAGS_TTL = 300
_monkey_tags: tuple[float, list[str]] = (0.0, [])


async def monkey_tags() -> list[str]:
    global _monkey_tags
    loaded, tags = _monkey_tags
    if loaded and time.monotonic() - loaded < MONKEY_TAGS_TTL:
        return tags
    try:
        from database.repository import library_summary

        tags = [row["tag"] for row in await library_summary() if row["tag"].startswith(MONKEY_STEMS)]
    except Exception as error:
        logger.error("MONKEY TAGS: %s %s", type(error).__name__, error)
        tags = []
    _monkey_tags = (time.monotonic(), tags)
    return tags


async def send_portrait(message: Message, name: str):
    """«Покажи меня»: котик или обезьянка — и подпись под того, кто выпал."""
    tags = await monkey_tags()
    if tags and random.random() < MONKEY_CHANCE:
        import images_library

        library = await images_library.pick(message.chat.id, "lib:" + random.choice(tags))
        if library is not None:
            try:
                await message.answer_photo(photo=library["file_id"], caption=pick_caption(name, monkey=True))
                return
            except Exception as error:
                logger.error("LIBRARY MONKEY: %s %s", type(error).__name__, error)

    await send_cat(message, pick_caption(name))


def is_show_me_request(message: Message) -> bool:
    if not is_enabled(message.chat.id, "cats"):
        return False

    if not message.text or message.text.startswith("/"):
        return False

    if not is_show_me(message.text):
        return False

    return is_addressed(message)


@router.message(is_show_me_request)
async def show_me_handler(message: Message):
    await send_portrait(message, escape(display_name_of(message.from_user)))


def is_meow_request(message: Message) -> bool:
    if not is_enabled(message.chat.id, "cats"):
        return False

    if not message.text or message.text.startswith("/"):
        return False

    if not is_meow(message.text):
        return False

    return is_addressed(message)


@router.message(is_meow_request)
async def meow_handler(message: Message):
    await send_cat(message, pick_meow_caption())


async def other_name(message: Message) -> str | None:
    """Кого показать: автор сообщения, на которое ответили, или @ник."""
    from botcontext import BOT_ID

    reply = message.reply_to_message
    if reply and reply.from_user and reply.from_user.id != BOT_ID and not reply.from_user.is_bot:
        return display_name_of(reply.from_user)

    import re

    match = re.search(r"@([A-Za-z0-9_]{3,32})", message.text or "")
    if not match:
        return None
    try:
        from database.repository import get_user_by_username

        user = await get_user_by_username(match.group(1))
        if user is not None and user.first_name:
            return user.first_name
    except Exception:
        pass
    return "@" + match.group(1)


def _has_target(message: Message) -> bool:
    from botcontext import BOT_ID

    reply = message.reply_to_message
    if reply and reply.from_user and reply.from_user.id != BOT_ID and not reply.from_user.is_bot:
        return True
    return "@" in (message.text or "")


def is_show_other_request(message: Message) -> bool:
    if not is_enabled(message.chat.id, "cats"):
        return False

    if not message.text or message.text.startswith("/"):
        return False

    if not is_show_other(message.text, _has_target(message)):
        return False

    # Обращение к Маре обязательно: «покажи @vasya» без имени — разговор людей
    from botcontext import TRIGGER_RE

    return bool(TRIGGER_RE.search(message.text)) or message.chat.type == "private"


@router.message(is_show_other_request)
async def show_other_handler(message: Message):
    name = await other_name(message)
    if not name:
        return
    await send_portrait(message, escape(name))
