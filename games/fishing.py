"""Telegram Mini App entry point for Maruska Fishing."""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, Message

from webapp.server import public_url

router = Router(name="fishing")
BOT_USERNAME = "BotMaruska_bot"


async def fishing_command(message: Message):
    base = public_url()
    if not base:
        await message.answer(
            "🎣 Рыбалка пока недоступна: у бота не настроен публичный HTTPS-адрес."
        )
        return

    if message.chat.type == "private":
        button = InlineKeyboardButton(
            text="🎣 Открыть рыбалку",
            web_app=WebAppInfo(url=f"{base}/fishing"),
        )
    else:
        # Telegram запрещает web_app-кнопки в групповых сообщениях.
        # Для группы используется Main Mini App deep link.
        button = InlineKeyboardButton(
            text="🎣 Открыть рыбалку",
            url=f"https://t.me/{BOT_USERNAME}?startapp=fishing",
        )

    kb = InlineKeyboardMarkup(inline_keyboard=[[button]])

    await message.answer(
        "🎣 <b>Маруська Fishing</b>\n\n"
        "Выбирай водоём, забрасывай удочку, вываживай рыбу и собирай коллекцию.",
        reply_markup=kb,
    )


@router.message(Command(commands=["fish", "fishing"]))
async def fishing_slash_command(message: Message):
    await fishing_command(message)


@router.message(F.text.casefold().in_({"рыбалка", "рыбачим", "рыбачка", "🎣 рыбалка"}))
async def fishing_text_command(message: Message):
    await fishing_command(message)
