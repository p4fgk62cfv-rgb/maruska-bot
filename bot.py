import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from ai.gemini import ask_gemini
from database.database import init_db
from database.repository import (
    save_user,
    save_message,
    get_recent_messages,
)


TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")


bot = Bot(token=TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message):

    await message.answer(
        "Привет! Я Маруська 💜\n"
        "Я уже подключила свой мозг и память 😉"
    )


@dp.message(Command("help"))
async def help_command(message: Message):

    await message.answer(
        "Команды:\n"
        "/start — запуск\n"
        "/help — помощь\n"
        "/ping — проверка связи\n\n"
        "Чтобы поговорить со мной, напиши "
        "«Маруська» или ответь на моё сообщение."
    )


@dp.message(Command("ping"))
async def ping(message: Message):

    await message.answer(
        "Маруська на связи 🟢"
    )


@dp.message()
async def ai_message(message: Message):

    if not message.text:
        return

    if message.from_user and message.from_user.is_bot:
        return

    if not message.from_user:
        return

    chat_id = message.chat.id
    telegram_user_id = message.from_user.id

    username = (
        message.from_user.first_name
        or message.from_user.username
        or "Пользователь"
    )

    # Сохраняем пользователя
    try:

        await save_user(
            telegram_id=telegram_user_id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )

    except Exception as e:

        print(
            "USER SAVE ERROR:",
            type(e).__name__,
            str(e),
        )

    # Сохраняем сообщение в PostgreSQL
    try:

        await save_message(
            chat_id=chat_id,
            telegram_user_id=telegram_user_id,
            username=username,
            message=message.text,
        )

    except Exception as e:

        print(
            "MESSAGE SAVE ERROR:",
            type(e).__name__,
            str(e),
        )

    text_lower = message.text.lower()

    mentioned = (
        "маруська" in text_lower
        or "@botmaruska_bot" in text_lower
    )

    replied_to_bot = (
        message.reply_to_message is not None
        and message.reply_to_message.from_user is not None
        and message.reply_to_message.from_user.id == bot.id
    )

    if not mentioned and not replied_to_bot:
        return

    # Получаем последние сообщения уже из PostgreSQL
    try:

        recent_messages = await get_recent_messages(
            chat_id=chat_id,
            limit=8,
        )

    except Exception as e:

        print(
            "MEMORY READ ERROR:",
            type(e).__name__,
            str(e),
        )

        recent_messages = []

    context = "\n".join(
        recent_messages
    )

    # Пока Google Search отключён
    use_search = False

    prompt = f"""
Последние сообщения в группе:

{context}

Текущее сообщение:
{username}: {message.text}

Ответь именно на текущее сообщение.

Учитывай контекст разговора.

Google Search сейчас отключён.

Не выдумывай факты.

Не говори о себе как о безличном ассистенте.
Ты — Маруська, участница этой компании.

Отвечай естественно.

Не обрывай ответ.
Закончи предложение и мысль полностью.
"""

    try:

        answer, sources = await ask_gemini(
            prompt,
            use_search=use_search,
        )

        answer = (
            answer or ""
        ).strip()

        if not answer:

            await message.answer(
                "Я почему-то не смогла сформулировать ответ 🤔"
            )

            return

        await message.answer(
            answer,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    except Exception as e:

        print(
            "========== GEMINI ERROR =========="
        )

        print(
            type(e).__name__,
            str(e)
        )

        print(
            "=================================="
        )

        error_text = str(e).lower()

        if (
            "quota" in error_text
            or "429" in error_text
            or "resource_exhausted" in error_text
        ):

            await message.answer(
                "Сейчас Gemini не принимает запросы 😴\n"
                "Попробуй немного позже."
            )

        else:

            await message.answer(
                "Что-то я сейчас задумалась 🤔"
            )


async def main():

    print(
        "==================================="
    )

    print(
        "Подключение к PostgreSQL..."
    )

    await init_db()

    print(
        "PostgreSQL подключён"
    )

    print(
        "МАРУСЬКА ЗАПУЩЕНА!"
    )

    print(
        "Gemini подключён"
    )

    print(
        "Google Search отключён"
    )

    print(
        "Постоянная память PostgreSQL включена"
    )

    print(
        "==================================="
    )

    await dp.start_polling(bot)


if __name__ == "__main__":

    asyncio.run(main())
