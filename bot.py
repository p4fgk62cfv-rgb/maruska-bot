import asyncio
import os
from html import escape

from aiogram import (
    Bot,
    Dispatcher,
)
from aiogram.filters import (
    Command,
    CommandStart,
)
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
    add_rating_vote,
    get_global_rating,
    get_rating_position,
    get_rating_stats,
)

from actions.handler import router as actions_router


# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv(
    "BOT_TOKEN"
)

if not TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set"
    )


bot = Bot(
    token=TOKEN
)

dp = Dispatcher()


# =========================================================
# RANKS
# =========================================================

def get_rank_info(
    karma: int,
):

    if karma >= 500:
        return "Легенда"

    if karma >= 250:
        return "Звезда"

    if karma >= 100:
        return "Авторитет"

    if karma >= 50:
        return "Уважаемый"

    if karma >= 10:
        return "Активист"

    return "Участник"


# =========================================================
# START
# =========================================================

@dp.message(
    CommandStart()
)
async def start_handler(
    message: Message,
):

    if message.from_user:

        await save_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )

        await create_profile_if_needed(
            telegram_id=message.from_user.id,
            display_name=(
                message.from_user.first_name
                or message.from_user.username
                or "Пользователь"
            ),
        )

    await message.answer(
        "👋 Привет! Я Маруська.\n\n"
        "Я могу общаться с вашей компанией, "
        "запоминать контекст, вести рейтинг "
        "и устраивать разные действия с картинками. 😏\n\n"
        "Например, ответь человеку на сообщение:\n"
        "<b>Пиво</b>\n\n"
        "И я отправлю случайную фотографию пива. 🍺",
        parse_mode="HTML",
    )


# =========================================================
# HELP
# =========================================================

@dp.message(
    Command("help")
)
async def help_handler(
    message: Message,
):

    await message.answer(
        "🤖 <b>Маруська</b>\n\n"
        "💬 Позови меня по имени — пообщаемся.\n\n"
        "⭐ <b>Рейтинг</b>\n"
        "+ или - в ответ на сообщение.\n\n"
        "👤 <b>Профиль</b>\n"
        "/profile\n\n"
        "🏆 <b>Топ</b>\n"
        "/top\n\n"
        "🎲 <b>Действия</b>\n"
        "Ответь человеку и напиши, например:\n"
        "🍺 Пиво\n"
        "☕ Кофе\n"
        "🍕 Пицца\n"
        "🌹 Цветы\n"
        "🎁 Подарок\n"
        "🤗 Обнять\n"
        "😘 Поцеловать\n\n"
        "Картинки будут меняться и не будут "
        "повторяться, пока не закончится "
        "текущая коллекция.",
        parse_mode="HTML",
    )


# =========================================================
# PING
# =========================================================

@dp.message(
    Command("ping")
)
async def ping_handler(
    message: Message,
):

    await message.answer(
        "🏓 Маруська работает."
    )


# =========================================================
# PROFILE
# =========================================================

@dp.message(
    Command("profile")
)
async def profile_handler(
    message: Message,
):

    if not message.from_user:
        return

    profile = await get_profile(
        message.from_user.id
    )

    if profile is None:

        await create_profile_if_needed(
            telegram_id=message.from_user.id,
            display_name=(
                message.from_user.first_name
                or message.from_user.username
                or "Пользователь"
            ),
        )

        profile = await get_profile(
            message.from_user.id
        )

    if profile is None:
        return

    position = await get_rating_position(
        message.from_user.id
    )

    stats = await get_rating_stats(
        message.from_user.id
    )

    rank = get_rank_info(
        profile.karma
    )

    name = escape(
        profile.display_name
        or "Пользователь"
    )

    await message.answer(
        f"👤 <b>{name}</b>\n\n"
        f"🎖 Ранг: <b>{rank}</b>\n"
        f"⭐ Рейтинг: <b>{profile.karma}</b>\n"
        f"🏆 Место: <b>#{position or '-'}</b>\n\n"
        f"💬 Сообщений: <b>{profile.messages_count}</b>\n"
        f"🎮 Игр: <b>{profile.games_played}</b>\n"
        f"🏅 Побед: <b>{profile.games_won}</b>\n\n"
        f"❤️ Положительных оценок: "
        f"<b>{stats['positive']}</b>\n"
        f"💔 Отрицательных оценок: "
        f"<b>{stats['negative']}</b>",
        parse_mode="HTML",
    )


# =========================================================
# RATING
# =========================================================

@dp.message()
async def rating_handler(
    message: Message,
):

    if not message.from_user:
        return

    if not message.text:
        return

    text = message.text.strip()

    if text not in (
        "+",
        "-",
    ):
        return

    if not message.reply_to_message:
        return

    target = (
        message.reply_to_message.from_user
    )

    if target is None:
        return

    if target.is_bot:
        return

    if target.id == message.from_user.id:

        await message.reply(
            "😏 Себе рейтинг накручивать нельзя."
        )

        return

    amount = (
        1
        if text == "+"
        else -1
    )

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

    allowed = await can_vote_rating(
        giver_telegram_id=message.from_user.id,
        target_telegram_id=target.id,
    )

    if not allowed:

        await message.reply(
            "⏳ Этого пользователя можно "
            "оценить снова через 24 часа."
        )

        return

    new_rating = await add_rating_vote(
        giver_telegram_id=message.from_user.id,
        target_telegram_id=target.id,
        amount=amount,
    )

    name = escape(
        target.first_name
        or target.username
        or "Пользователь"
    )

    rank = get_rank_info(
        new_rating
    )

    if amount > 0:

        await message.reply(
            f"❤️ <b>Лайк!</b>\n\n"
            f"Рейтинг пользователя "
            f"<b>{name}</b> повышен на "
            f"<b>+1</b>.\n\n"
            f"❤️ Теперь рейтинг: "
            f"<b>{new_rating}</b>\n"
            f"🎖 Ранг: <b>{rank}</b>",
            parse_mode="HTML",
        )

    else:

        await message.reply(
            f"💔 <b>Минус!</b>\n\n"
            f"Рейтинг пользователя "
            f"<b>{name}</b> понижен на "
            f"<b>-1</b>.\n\n"
            f"⭐ Теперь рейтинг: "
            f"<b>{new_rating}</b>\n"
            f"🎖 Ранг: <b>{rank}</b>",
            parse_mode="HTML",
        )


# =========================================================
# TOP
# =========================================================

@dp.message(
    Command("top")
)
async def top_handler(
    message: Message,
):

    users = await get_global_rating(
        limit=10
    )

    if not users:

        await message.answer(
            "🏆 Пока рейтинг пуст."
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

    for index, user in enumerate(
        users,
        start=1,
    ):

        medal = (
            medals[index - 1]
            if index <= 3
            else f"{index}."
        )

        name = escape(
            user.display_name
            or "Пользователь"
        )

        rank = get_rank_info(
            user.karma
        )

        lines.append(
            f"{medal} "
            f"<b>{name}</b> — "
            f"{user.karma} ⭐ "
            f"({rank})"
        )

    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
    )


# =========================================================
# AI CHAT
# =========================================================

@dp.message()
async def ai_handler(
    message: Message,
):

    if not message.from_user:
        return

    if not message.text:
        return

    if message.from_user.is_bot:
        return

    # Если это команда/рейтинг — ничего не делаем.
    if message.text.startswith("/"):
        return

    # Сохраняем пользователя
    await save_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    await save_message(
        chat_id=message.chat.id,
        telegram_user_id=message.from_user.id,
        username=(
            message.from_user.first_name
            or message.from_user.username
        ),
        message=message.text,
    )

    text_lower = message.text.lower()

    bot_username = (
        (await bot.get_me()).username
        or "botmaruska_bot"
    )

    should_answer = (
        "маруська" in text_lower
        or f"@{bot_username.lower()}"
        in text_lower
    )

    if message.reply_to_message:

        if (
            message.reply_to_message.from_user
            and
            message.reply_to_message.from_user.id
            == bot.id
        ):

            should_answer = True

    if not should_answer:
        return

    recent_messages = await get_recent_messages(
        message.chat.id,
        limit=8,
    )

    context = "\n".join(
        recent_messages
    )

    prompt = (
        "Последние сообщения группы:\n"
        f"{context}\n\n"
        "Новое сообщение пользователя:\n"
        f"{message.text}"
    )

    try:

        answer, sources = await ask_gemini(
            prompt,
            use_search=False,
        )

    except Exception as error:

        print(
            "GEMINI ERROR:",
            type(error).__name__,
            str(error),
        )

        await message.reply(
            "Что-то я задумалась 🤔"
        )

        return

    if not answer:
        return

    await message.reply(
        answer
    )


# =========================================================
# MAIN
# =========================================================

async def main():

    print(
        "================================"
    )

    print(
        "МАРУСЬКА ЗАПУСКАЕТСЯ..."
    )

    print(
        "================================"
    )

    await init_db()

    print(
        "DATABASE: PostgreSQL подключён"
    )

    print(
        "Gemini: подключён"
    )

    if os.getenv(
        "UNSPLASH_ACCESS_KEY"
    ):

        print(
            "Unsplash: подключён"
        )

    else:

        print(
            "Unsplash: НЕ подключён"
        )

    print(
        "Действия с картинками: включены"
    )

    print(
        "Постоянная память PostgreSQL: включена"
    )

    print(
        "Глобальный рейтинг: включён"
    )

    # Сначала действия.
    # Они должны перехватываться раньше AI.
    dp.include_router(
        actions_router
    )

    print(
        "МАРУСЬКА ЗАПУЩЕНА!"
    )

    await dp.start_polling(
        bot
    )


if __name__ == "__main__":

    asyncio.run(
        main()
    )
