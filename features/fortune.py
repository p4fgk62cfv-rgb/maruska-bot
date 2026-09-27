"""
Предсказания: «Мара, предскажи».

Стиль предсказаний задаётся администратором в настройках (fortune_mode).
Пользователь не выбирает — просто получает предсказание.
"""

from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

import fortune

from botcontext import display_name_of, is_addressed

from settings.store import get_value, is_enabled

router = Router(name="fortune")


def is_fortune_request(message: Message) -> bool:
    if not is_enabled(message.chat.id, "fortune"):
        return False

    if not message.text or message.text.startswith("/"):
        return False

    if not fortune.mentions_fortune(message.text):
        return False

    return is_addressed(message)


@router.message(Command("fortune", "predict", "future"))
async def fortune_command(message: Message):
    if not is_enabled(message.chat.id, "fortune"):
        await message.reply("🔮 Предсказания в этой группе выключены (/settings).")
        return

    await send_fortune(message)


@router.message(is_fortune_request)
async def fortune_handler(message: Message):
    await send_fortune(message)


_MODE_FLAGS = {"sarcasm": "fortune_sarcasm", "vulgar": "fortune_vulgar", "brutal": "fortune_brutal"}


def _sanitize_mode(chat_id: int, mode: str) -> str:
    flag = _MODE_FLAGS.get(mode)
    if flag and not is_enabled(chat_id, flag):
        return "roast"
    return mode


async def send_fortune(message: Message):
    user = message.from_user

    if user is None or user.is_bot:
        return

    chat_id = message.chat.id
    mode = _sanitize_mode(chat_id, get_value(chat_id, "fortune_mode") or "roast")

    await message.reply(
        fortune.predict(
            user.id,
            escape(display_name_of(user)),
            mode=mode,
        ),
    )
