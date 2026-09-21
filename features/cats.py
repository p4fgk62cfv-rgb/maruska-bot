"""
Котики: «покажи меня» и «мяу».
"""

import logging
from html import escape

from aiogram import Router
from aiogram.types import BufferedInputFile, Message

from actions.providers import download_photo
from actions.service import get_image_for_action
from actions.show_me import (
    is_meow,
    is_show_me,
    pick_caption,
    pick_meow_caption,
    pick_mood,
)

from botcontext import display_name_of, is_addressed

from database.repository import (
    drop_action_image,
    release_action_image,
    set_action_image_file_id,
)

from settings.store import is_enabled

logger = logging.getLogger("maruska.cats")

router = Router(name="cats")


async def send_cat(message: Message, caption: str):
    try:
        await message.bot.send_chat_action(message.chat.id, "upload_photo")
    except Exception:
        pass

    mood = pick_mood()

    try:
        image = await get_image_for_action(mood)
    except Exception as error:
        logger.error("CAT: %s %s", type(error).__name__, error)
        image = None

    if image is None:
        await message.reply("Котики закончились, попробуй попозже 🐾")
        return

    if image.telegram_file_id:
        try:
            await message.reply_photo(
                photo=image.telegram_file_id,
                caption=caption,
            )
            return
        except Exception as error:
            logger.warning("CAT file_id: %s", error)

    content = await download_photo(image.image_url, image.fallback_url)

    if content is None:
        await drop_action_image(image.id)
        await message.reply("Котик не загрузился 🐾")
        return

    try:
        sent = await message.reply_photo(
            photo=BufferedInputFile(content, filename="cat.jpg"),
            caption=caption,
        )
    except Exception as error:
        logger.warning("CAT send: %s", error)
        await release_action_image(image.id)
        await message.reply("Котик не отправился 🐾")
        return

    if sent.photo:
        try:
            await set_action_image_file_id(image.id, sent.photo[-1].file_id)
        except Exception:
            pass


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
