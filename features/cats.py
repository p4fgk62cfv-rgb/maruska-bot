"""
Котики: «покажи меня» и «мяу».
"""

import logging
from html import escape

from aiogram import Router
from aiogram.types import Message

from actions.handler import send_picked
from actions.service import get_image_for_action
from actions.show_me import (
    is_meow,
    is_show_me,
    pick_caption,
    pick_meow_caption,
    pick_mood,
)

from botcontext import display_name_of, is_addressed

from settings.store import is_enabled

logger = logging.getLogger("maruska.cats")

router = Router(name="cats")


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

    mood = pick_mood()

    try:
        picked = await get_image_for_action(mood)
    except Exception as error:
        logger.error("CAT: %s %s", type(error).__name__, error)
        picked = None

    if picked is None:
        await message.reply("Котики закончились, попробуй попозже 🐾")
        return

    sent = await send_picked(message, picked, caption, "cat")

    if sent is None:
        await message.reply("Котик не отправился 🐾")


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
    await send_cat(
        message,
        pick_caption(escape(display_name_of(message.from_user))),
    )


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
