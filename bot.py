import asyncio
import os
import re

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from ai.gemini import ask_gemini
from database.database import init_db
from database.repository import (
    save_user,
    save_message,
    get_recent_messages,
    get_profile,
    create_profile_if_needed,
    change_karma,
    get_global_rating,
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
        "/ping — проверка связи\n"
        "/profile — твой профиль\n"
        "/rating — глобальный рейтинг кармы\n\n"
        "Карма:\n"
        "Ответь на сообщение человека и напиши "
        "+карма или -карма.\n\n"
        "Также можно:\n"
        "+карма @username\n"
        "-карма @username\n\n"
        "Чтобы поговорить со мной, напиши "
        "«Маруська» или ответь на моё сообщение."
    )


@dp.message(Command("ping"))
async def ping(message: Message):

    await message.answer(
        "Маруська на связи 🟢"
    )


@dp.message(Command("profile"))
async def profile_command(message: Message):

    if not message.from_user:
        return

    telegram_id = message.from_user.id

    display_name = (
        message.from_user.first_name
        or message.from_user.username
        or "Пользователь"
    )

    try:

        await create_profile_if_needed(
            telegram_id=telegram_id,
            display_name=display_name,
        )

        profile = await get_profile(
            telegram_id=telegram_id,
        )

        if profile is None:

            await message.answer(
                "Не смогла загрузить профиль 🤔"
            )

            return

        await message.answer(
            f"👤 <b>{profile.display_name or display_name}</b>\n\n"
            f"⭐ Карма: <b>{profile.karma}</b>\n"
            f"🪙 Монеты: <b>{profile.coins}</b>\n"
            f"💬 Сообщений: <b>{profile.messages_count}</b>\n\n"
            f"🎮 Игр сыграно: <b>{profile.games_played}</b>\n"
            f"🏆 Побед: <b>{profile.games_won}</b>",
            parse_mode="HTML",
        )

    except Exception as e:

        print(
            "PROFILE ERROR:",
            type(e).__name__,
            str(e),
        )

        await message.answer(
            "Не смогла загрузить профиль 🤔"
        )


async def find_karma_target(
    message: Message,
    username: str | None,
):
    """
    Определяет пользователя, которому меняем карму.

    Приоритет:
    1. Ответ на сообщение.
    2. @username.
    """

    if (
        message.reply_to_message
        and message.reply_to_message.from_user
    ):
        return message.reply_to_message.from_user

    if not username:
        return None

    username = username.lstrip("@").lower()

    from sqlalchemy import select
    from database.database import get_session
    from database.models import User

    async for session in get_session():

        result = await session.execute(
            select(User).where(
                User.username.ilike(username)
            )
        )

        return result.scalar_one_or_none()

    return None


@dp.message(
    lambda message:
    message.text
    and re.match(
        r"^[+-]карма(?:\s+@?([A-Za-z0-9_]{1,32}))?\s*$",
        message.text.strip(),
        re.IGNORECASE,
    )
)
async def karma_command(message: Message):

    if not message.from_user:
        return

    text = message.text.strip()

    match = re.match(
        r"^([+-])карма(?:\s+@?([A-Za-z0-9_]{1,32}))?\s*$",
        text,
        re.IGNORECASE,
    )

    if not match:
        return

    sign = match.group(1)
    username = match.group(2)

    target = await find_karma_target(
        message,
        username,
    )

    if target is None:

        await message.answer(
            "Не поняла, кому изменить карму 🤔\n\n"
            "Ответь на сообщение человека и напиши "
            "+карма или -карма."
        )

        return

    target_id = target.id
    giver_id = message.from_user.id

    if target_id == giver_id:

        await message.answer(
            "Самому себе карму нельзя 😏"
        )

        return

    if getattr(target, "is_bot", False):

        await message.answer(
            "Ботам карму пока не выдаём 🤖"
        )

        return

    amount = 1 if sign == "+" else -1

    try:

        new_karma = await change_karma(
            telegram_id=target_id,
            amount=amount,
        )

        target_name = (
            target.first_name
            or target.username
            or "Пользователь"
        )

        emoji = "⭐" if amount > 0 else "💥"

        await message.answer(
            f"{emoji} {target_name}: "
            f"карма {'+' if amount > 0 else ''}{amount}\n"
            f"Теперь карма: <b>{new_karma}</b>"
        )

    except Exception as e:

        print(
            "KARMA ERROR:",
            type(e).__name__,
            str(e),
        )

        await message.answer(
            "Не смогла изменить карму 🤔"
        )


@dp.message(Command("rating"))
async def rating_command(message: Message):

    try:

        users = await get_global_rating(
            limit=10,
        )

        if not users:

            await message.answer(
                "Пока рейтинг пуст 🏆"
            )

            return

        lines = [
            "🏆 <b>Глобальный рейтинг Маруськи</b>\n"
        ]

        medals = [
            "🥇",
            "🥈",
            "🥉",
        ]

        for index, user in enumerate(users):

            if index < 3:
                medal = medals[index]
            else:
                medal = f"{index + 1}."

            name = (
                user.display_name
                or f"ID {user.telegram_id}"
            )

            lines.append(
                f"{medal} {name} — "
                f"⭐ <b>{user.karma}</b>"
            )

        await message.answer(
            "\n".join(lines),
            parse_mode="HTML",
        )

    except Exception as e:

        print(
            "RATING ERROR:",
            type(e).__name__,
            str(e),
        )

        await message.answer(
            "Не смогла загрузить рейтинг 🤔"
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
        "Профили пользователей включены"
    )

    print(
        "Глобальная карма включена"
    )

    print(
        "==================================="
    )

    await dp.start_polling(bot)


if __name__ == "__main__":

    asyncio.run(main())
