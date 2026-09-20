import asyncio
import os
from html import escape

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
    can_vote_rating,
    get_last_rating_vote,
    add_rating_vote,
    get_global_rating,
    get_rating_position,
)


TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")


bot = Bot(token=TOKEN)
dp = Dispatcher()


def get_rank(rating: int):

    if rating >= 500:
        return "Легенда 🏆"

    if rating >= 250:
        return "Звезда ⭐"

    if rating >= 100:
        return "Авторитет 👑"

    if rating >= 50:
        return "Уважаемый 💎"

    if rating >= 10:
        return "Активист 🔥"

    return "Пользователь"


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
        "/profile — профиль\n"
        "/rating — глобальный рейтинг\n\n"
        "❤️ Рейтинг:\n"
        "Ответь на сообщение человека и отправь + или -.\n\n"
        "Один человек может изменить рейтинг другого "
        "не чаще одного раза в 24 часа."
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

        rating = profile.karma

        rank = get_rank(rating)

        position = await get_rating_position(
            telegram_id=telegram_id,
        )

        name = escape(
            profile.display_name
            or display_name
        )

        position_text = (
            f"🏆 Место: <b>#{position}</b>\n"
            if position
            else ""
        )

        await message.answer(
            f"👤 <b>{name}</b>\n\n"
            f"❤️ Рейтинг: <b>{rating}</b>\n"
            f"🎖 Ранг: <b>{rank}</b>\n"
            f"{position_text}"
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
            "🏆 <b>Глобальный рейтинг</b>\n"
        ]

        medals = [
            "🥇",
            "🥈",
            "🥉",
        ]

        for index, user in enumerate(users):

            rating = user.karma

            rank = get_rank(rating)

            name = escape(
                user.display_name
                or f"ID {user.telegram_id}"
            )

            if index < 3:
                prefix = medals[index]
            else:
                prefix = f"{index + 1}."

            lines.append(
                f"{prefix} <b>{name}</b>\n"
                f"   ❤️ {rating} · {rank}"
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


@dp.message(
    lambda message:
    message.text
    and message.text.strip() in ("+", "-")
    and message.reply_to_message is not None
)
async def rating_vote(message: Message):

    if not message.from_user:
        return

    target_message = message.reply_to_message

    if not target_message:
        return

    target_user = target_message.from_user

    if not target_user:

        await message.answer(
            "Не смогла определить пользователя 🤔"
        )

        return

    giver_id = message.from_user.id
    target_id = target_user.id

    if giver_id == target_id:

        await message.answer(
            "Самому себе рейтинг нельзя 😏"
        )

        return

    if target_user.is_bot:

        await message.answer(
            "Ботам рейтинг пока не выдаём 🤖"
        )

        return

    amount = (
        1
        if message.text.strip() == "+"
        else -1
    )

    try:

        allowed = await can_vote_rating(
            giver_telegram_id=giver_id,
            target_telegram_id=target_id,
        )

        if not allowed:

            last_vote = await get_last_rating_vote(
                giver_telegram_id=giver_id,
                target_telegram_id=target_id,
            )

            if last_vote:

                await message.answer(
                    "Ты уже изменял рейтинг этого "
                    "пользователя за последние 24 часа ⏳\n\n"
                    "Попробуй позже."
                )

            else:

                await message.answer(
                    "Этот рейтинг пока нельзя изменить ⏳"
                )

            return

        new_rating = await add_rating_vote(
            giver_telegram_id=giver_id,
            target_telegram_id=target_id,
            amount=amount,
        )

        target_name = escape(
            target_user.first_name
            or target_user.username
            or "Пользователь"
        )

        rank = get_rank(new_rating)

        if amount > 0:

            await message.answer(
                f"❤️ <b>Лайк!</b>\n\n"
                f"Рейтинг пользователя "
                f"<b>{target_name}</b> повышен на "
                f"<b>+1</b>.\n\n"
                f"❤️ Теперь рейтинг: "
                f"<b>{new_rating}</b>\n"
                f"🎖 Ранг: <b>{rank}</b>",
                parse_mode="HTML",
            )

        else:

            await message.answer(
                f"👎 <b>Рейтинг понижен</b>\n\n"
                f"Рейтинг пользователя "
                f"<b>{target_name}</b> изменён на "
                f"<b>-1</b>.\n\n"
                f"❤️ Теперь рейтинг: "
                f"<b>{new_rating}</b>\n"
                f"🎖 Ранг: <b>{rank}</b>",
                parse_mode="HTML",
            )

    except Exception as e:

        print(
            "RATING VOTE ERROR:",
            type(e).__name__,
            str(e),
        )

        await message.answer(
            "Не смогла изменить рейтинг 🤔"
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

    prompt = f"""
Последние сообщения в группе:

{context}

Текущее сообщение:
{username}: {message.text}

Ответь именно на текущее сообщение.

Учитывай контекст разговора.

Google Search сейчас отключён.

Не выдумывай факты.

Ты — Маруська, участница этой компании.

Отвечай естественно.

Не обрывай ответ.
Закончи предложение и мысль полностью.
"""

    try:

        answer, sources = await ask_gemini(
            prompt,
            use_search=False,
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
            str(e),
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
        "Глобальный рейтинг включён"
    )

    print(
        "История рейтинга включена"
    )

    print(
        "Антинакрутка рейтинга: 24 часа"
    )

    print(
        "==================================="
    )

    await dp.start_polling(bot)


if __name__ == "__main__":

    asyncio.run(main())
