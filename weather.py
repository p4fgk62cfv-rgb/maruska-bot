"""
Погода: команда и обращение вида «Мара, погода в Праге».
"""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from botcontext import is_addressed

from settings.store import is_enabled

from weather import (
    DEFAULT_CITY,
    extract_city,
    get_weather_text,
    mentions_weather,
)

router = Router(name="weather")


@router.message(Command("weather", "pogoda"))
async def weather_command(message: Message):
    if not is_enabled(message.chat.id, "weather"):
        await message.reply("🌤 Погода в этой группе выключена (/settings).")
        return

    args = message.text.split(maxsplit=1)
    city = args[1].strip() if len(args) > 1 else DEFAULT_CITY

    await message.answer(await get_weather_text(city))


def is_weather_question(message: Message) -> bool:
    if not is_enabled(message.chat.id, "weather"):
        return False

    if not message.text or message.text.startswith("/"):
        return False

    if not mentions_weather(message.text):
        return False

    return is_addressed(message)


@router.message(is_weather_question)
async def weather_handler(message: Message):
    await message.answer(await get_weather_text(extract_city(message.text)))
