import asyncio
import logging
import os
import re
from html import escape

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, Message

from ai.gemini import ask_gemini

from database.database import init_db, close_db

from database.repository import (
    get_balance,
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
from games.crocodile import (
    drawing_enabled,
    restore_rounds,
    router as crocodile_router,
    set_bot_username,
)

from webapp.server import public_url, start_web_server
from actions.providers import available_providers, download_photo
from actions.service import get_image_for_action
from actions.show_me import (
    is_meow,
    is_show_me,
    pick_caption,
    pick_meow_caption,
    pick_mood,
)

from database.repository import (
    set_action_image_file_id,
    release_action_image,
    drop_action_image,
)

import context_cache

from economy.handler import router as economy_router
from economy.service import CURRENCY, money, wealth_title

from settings.handler import router as settings_router
from settings.middleware import SettingsMiddleware
from settings.store import is_enabled

from weather import (
    DEFAULT_CITY,
    extract_city,
    get_weather_text,
    mentions_weather,
)


import logging_setup

logging_setup.setup()

logger = logging.getLogger("maruska")


# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

CONTEXT_MESSAGES = int(os.getenv("CONTEXT_MESSAGES", "8"))

# Имена, на которые бот откликается в группе.
# Принимаются любые падежные формы: Мара, Мару, Маре, Марой,
# а также Маруся и Маруська. Сравнение идёт по целому слову,
# поэтому "Тамара", "Самара" и "кошмара" бота не будят.
TRIGGER_PATTERN = r"мар(?:а|у|ы|е|ой|ою|ке|ку)|марус(?:я|ю|е|и|ька|ьку|ьке)|маня"

TRIGGER_RE = re.compile(r"\b(?:" + TRIGGER_PATTERN + r")\b", re.IGNORECASE)


bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

dp = Dispatcher()

root_router = Router(name="root")


# Идентичность бота кэшируется один раз при старте,
# вместо get_me() на каждое входящее сообщение.
BOT_ID: int = 0
BOT_USERNAME: str = ""


# =========================================================
# RANKS
# =========================================================

def get_rank_info(karma: int) -> str:
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


def display_name_of(user) -> str:
    return user.first_name or user.username or "Пользователь"


# =========================================================
# START
# =========================================================

@root_router.message(CommandStart())
async def start_handler(message: Message):
    if message.from_user:
        await save_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )

        await create_profile_if_needed(
            telegram_id=message.from_user.id,
            display_name=display_name_of(message.from_user),
        )

    await message.answer(
        "👋 Привет! Я Маруська.\n\n"
        "Я могу общаться с вашей компанией, запоминать контекст, "
        "вести рейтинг и устраивать разные действия с картинками. 😏\n\n"
        "Например, ответь человеку на сообщение:\n"
        "<b>Пиво</b>\n\n"
        "И я отправлю случайную фотографию пива. 🍺"
    )


# =========================================================
# HELP
# =========================================================

@root_router.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(
        "🤖 <b>Маруська</b>\n\n"
        "💬 Позови по имени: <b>Мара, ...</b>\n"
        "Или ответь на моё сообщение.\n\n"
        "🐱 <b>Котики</b>\n"
        "Мара, покажи меня — портрет по мотивам котиков\n"
        "Мара, мяу — просто котик\n\n"
        "💎 <b>Алмазы</b>\n"
        "/bonus — ежедневный бонус\n"
        "/balance — баланс\n"
        "/history — последние операции\n"
        "/rich — топ богачей\n\n"
        "⚙️ <b>Настройки</b>\n"
        "/settings — включить или выключить функции (для админов)\n"
        "/features — что сейчас включено\n"
        "/myid — узнать свой ID\n\n"
        "🐊 <b>Крокодил</b>\n"
        "Напиши «крокодил» — начнётся раунд.\n"
        "Ведущий рисует на холсте, остальные отгадывают.\n"
        "/stopgame — остановить\n\n"
        "🌤 <b>Погода</b>\n"
        "Мара, погода в Праге?\n"
        "или /weather Прага\n\n"
        "⭐ <b>Рейтинг</b>\n"
        "+ или - в ответ на сообщение.\n\n"
        "👤 <b>Профиль</b>\n/profile\n\n"
        "🏆 <b>Топ</b>\n/top\n\n"
        "🎲 <b>Действия</b>\n"
        "Ответь человеку и напиши одним-двумя словами:\n\n"
        "🍺 Пиво, водка, вино, самогон, мохито\n"
        "☕ Кофе, чай, какао, квас, смузи\n"
        "🍕 Пицца, шаурма, борщ, пельмени, суши\n"
        "🍰 Торт, мороженое, пряник, халва\n"
        "🍓 Клубника, арбуз, манго, хурма\n"
        "🌹 Розы, пионы, ромашки, кактус\n"
        "🎁 Подарок, мишку, миллион, корону\n"
        "🐱 Котика, щенка, хомяка, попугая\n"
        "🚑 Дурку, скорую, такси, пожарных\n"
        "🤗 Обнять, целую, на ручки, погладить\n"
        "🧖 Баня, рыбалка, спортзал, селфи\n\n"
        "Больше 200 вариантов, фразы каждый раз разные.\n"
        "Срабатываю только на короткой фразе — обычная "
        "переписка меня не разбудит."
    )


# =========================================================
# PING
# =========================================================

@root_router.message(Command("ping"))
async def ping_handler(message: Message):
    await message.answer("🏓 Мара на связи.")


# =========================================================
# PROFILE
# =========================================================

@root_router.message(Command("profile"))
async def profile_handler(message: Message):
    if not message.from_user:
        return

    profile = await get_profile(message.from_user.id)

    if profile is None:
        await create_profile_if_needed(
            telegram_id=message.from_user.id,
            display_name=display_name_of(message.from_user),
        )
        profile = await get_profile(message.from_user.id)

    if profile is None:
        return

    position = await get_rating_position(message.from_user.id)
    stats = await get_rating_stats(message.from_user.id)

    name = escape(profile.display_name or "Пользователь")

    wallet = ""

    if is_enabled(message.chat.id, "economy"):
        balance = await get_balance(message.from_user.id)
        wallet = (
            f"{CURRENCY} Алмазы: <b>{money(balance)}</b> "
            f"({wealth_title(balance)})\n"
        )

        if profile.bonus_streak:
            wallet += f"🔥 Серия бонусов: <b>{profile.bonus_streak}</b>\n"

        wallet += "\n"

    await message.answer(
        f"👤 <b>{name}</b>\n\n"
        f"🎖 Ранг: <b>{get_rank_info(profile.karma)}</b>\n"
        f"⭐ Рейтинг: <b>{profile.karma}</b>\n"
        f"🏆 Место: <b>#{position or '-'}</b>\n\n"
        f"{wallet}"
        f"💬 Сообщений: <b>{profile.messages_count}</b>\n"
        f"🎮 Игр: <b>{profile.games_played}</b>\n"
        f"🏅 Побед: <b>{profile.games_won}</b>\n\n"
        f"❤️ Положительных оценок: <b>{stats['positive']}</b>\n"
        f"💔 Отрицательных оценок: <b>{stats['negative']}</b>"
    )


# =========================================================
# RATING (+ / -)
# =========================================================

def is_rating_message(message: Message) -> bool:
    if not is_enabled(message.chat.id, "rating"):
        return False

    return (
        message.text is not None
        and message.text.strip() in {"+", "-", "＋", "−"}
    )


@root_router.message(is_rating_message)
async def rating_handler(message: Message):
    if not message.from_user or not message.reply_to_message:
        return

    target = message.reply_to_message.from_user

    if target is None or target.is_bot:
        return

    if target.id == message.from_user.id:
        await message.reply("😏 Себе рейтинг накручивать нельзя.")
        return

    amount = 1 if message.text.strip() in {"+", "＋"} else -1

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

    if not await can_vote_rating(
        giver_telegram_id=message.from_user.id,
        target_telegram_id=target.id,
    ):
        await message.reply(
            "⏳ Этого пользователя можно оценить снова через 24 часа."
        )
        return

    target_name = display_name_of(target)

    new_rating = await add_rating_vote(
        giver_telegram_id=message.from_user.id,
        target_telegram_id=target.id,
        amount=amount,
        display_name=target_name,
    )

    name = escape(target_name)
    rank = get_rank_info(new_rating)

    if amount > 0:
        await message.reply(
            f"❤️ <b>Лайк!</b>\n\n"
            f"Рейтинг пользователя <b>{name}</b> повышен на <b>+1</b>.\n\n"
            f"⭐ Теперь рейтинг: <b>{new_rating}</b>\n"
            f"🎖 Ранг: <b>{rank}</b>"
        )
    else:
        await message.reply(
            f"💔 <b>Минус!</b>\n\n"
            f"Рейтинг пользователя <b>{name}</b> понижен на <b>-1</b>.\n\n"
            f"⭐ Теперь рейтинг: <b>{new_rating}</b>\n"
            f"🎖 Ранг: <b>{rank}</b>"
        )


# =========================================================
# TOP
# =========================================================

@root_router.message(Command("top"))
async def top_handler(message: Message):
    if not is_enabled(message.chat.id, "rating"):
        await message.reply("⭐ Рейтинг в этой группе выключен (/settings).")
        return

    users = await get_global_rating(limit=10)

    if not users:
        await message.answer("🏆 Пока рейтинг пуст.")
        return

    lines = ["🏆 <b>Глобальный рейтинг</b>\n"]
    medals = ["🥇", "🥈", "🥉"]

    for index, user in enumerate(users, start=1):
        medal = medals[index - 1] if index <= 3 else f"{index}."
        name = escape(user.display_name or "Пользователь")
        lines.append(
            f"{medal} <b>{name}</b> — {user.karma} ⭐ "
            f"({get_rank_info(user.karma)})"
        )

    await message.answer("\n".join(lines))


def is_addressed(message: Message) -> bool:
    """
    Обратились ли к боту: по имени, через @упоминание или
    ответом на его сообщение.

    Намеренно НЕ смотрит на настройку "ai": погода и котики
    вызываются тем же обращением, но живут по своим флагам.
    Иначе выключение ответов Мары молча убивало бы и их.
    """
    text = message.text or ""

    if message.chat.type == "private":
        return True

    if TRIGGER_RE.search(text):
        return True

    if BOT_USERNAME and f"@{BOT_USERNAME.lower()}" in text.lower():
        return True

    reply = message.reply_to_message

    if reply and reply.from_user and reply.from_user.id == BOT_ID:
        return True

    return False


def should_answer(message: Message) -> bool:
    """Нужен ли AI-ответ: обращение плюс включённая функция."""
    return is_enabled(message.chat.id, "ai") and is_addressed(message)


# =========================================================
# ПОГОДА
# =========================================================
#
# Open-Meteo, ключ не нужен. Срабатывает на /weather
# и на обращение вида "Мару, погода в Праге?".
#
# =========================================================

@root_router.message(Command("weather", "pogoda"))
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


@root_router.message(is_weather_question)
async def weather_handler(message: Message):
    await message.answer(await get_weather_text(extract_city(message.text)))


# =========================================================
# ПОКАЖИ МЕНЯ
# =========================================================
#
# "Мара, покажи меня" -> случайный котик как портрет.
#
# =========================================================

async def send_cat(message: Message, caption: str):
    try:
        await bot.send_chat_action(message.chat.id, "upload_photo")
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


@root_router.message(is_show_me_request)
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


@root_router.message(is_meow_request)
async def meow_handler(message: Message):
    await send_cat(message, pick_meow_caption())


# =========================================================
# AI CHAT
# =========================================================
#
# Действия обрабатываются в actions_router, который подключён
# ПЕРЕД этим роутером. Если сообщение — действие с адресатом,
# сюда оно уже не дойдёт. Всё остальное приходит к Маруське.
#
# =========================================================

@root_router.message(lambda message: message.text is not None)
async def ai_handler(message: Message):
    if not message.from_user or message.from_user.is_bot:
        return

    # Неизвестные команды в Gemini не отправляем.
    if message.text.startswith("/"):
        return

    name = display_name_of(message.from_user)

    # Контекст держим в памяти: чтение из базы перед каждым
    # ответом добавляло заметную задержку.
    context_cache.remember(message.chat.id, name, message.text)

    # Запись в базу не задерживает ответ — уходит в фон.
    asyncio.create_task(
        persist_message(message, name)
    )

    if not should_answer(message):
        return

    # Показываем "печатает..." сразу, чтобы ожидание не было немым.
    try:
        await bot.send_chat_action(message.chat.id, "typing")
    except Exception:
        pass

    if not context_cache.is_loaded(message.chat.id):
        try:
            history = await get_recent_messages(
                message.chat.id,
                limit=CONTEXT_MESSAGES,
            )
            context_cache.prime(message.chat.id, history)
        except Exception as error:
            logger.warning("CONTEXT LOAD: %s", error)
            context_cache.prime(message.chat.id, [])

    recent_messages = context_cache.recent(
        message.chat.id,
        CONTEXT_MESSAGES,
    )

    prompt = (
        "Последние сообщения группы:\n"
        + "\n".join(recent_messages)
        + "\n\nНовое сообщение пользователя:\n"
        + message.text
    )

    try:
        answer, _sources = await ask_gemini(prompt, use_search=False)
    except Exception as error:
        logger.error("GEMINI ERROR: %s %s", type(error).__name__, error)
        await message.reply("Что-то я задумалась 🤔")
        return

    if not answer:
        return

    context_cache.remember(message.chat.id, "Мара", answer)

    # Ответ модели — обычный текст, HTML-разметку из него не парсим.
    await message.reply(answer, parse_mode=None)


async def persist_message(message: Message, name: str):
    """
    Сохранение пользователя и сообщения в базу, вне критического пути.
    """
    try:
        await save_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )

        await save_message(
            chat_id=message.chat.id,
            telegram_user_id=message.from_user.id,
            username=name,
            message=message.text,
        )
    except Exception as error:
        logger.warning(
            "PERSIST: %s %s", type(error).__name__, error
        )


# =========================================================
# ROUTERS
# =========================================================
#
# Порядок важен: сначала действия, потом всё остальное.
#
# =========================================================

# Настройки читаются до фильтров, иначе выключенные функции
# успеют сработать.
dp.message.outer_middleware(SettingsMiddleware())
dp.callback_query.outer_middleware(SettingsMiddleware())

# Панель идёт первой: /settings должен работать всегда,
# даже если всё остальное выключено.
dp.include_router(settings_router)
dp.include_router(economy_router)

# Игра раньше действий: во время раунда верная отгадка должна
# перехватываться первой.
dp.include_router(crocodile_router)
dp.include_router(actions_router)
dp.include_router(root_router)


# =========================================================
# MAIN
# =========================================================

async def main():
    global BOT_ID, BOT_USERNAME

    logger.info("МАРУСЬКА ЗАПУСКАЕТСЯ...")

    await init_db()

    me = await bot.get_me()
    BOT_ID = me.id
    BOT_USERNAME = me.username or ""
    set_bot_username(BOT_USERNAME)

    logger.info("Бот: @%s (id=%s)", BOT_USERNAME, BOT_ID)
    logger.info("PostgreSQL: подключён")
    logger.info("Gemini: подключён")
    providers = available_providers()
    logger.info(
        "Картинки: %s",
        ", ".join(providers) if providers else "НИ ОДИН ИСТОЧНИК НЕ НАСТРОЕН",
    )
    restored = await restore_rounds()
    if restored:
        logger.info("Восстановлено раундов: %s", restored)

    # Веб-сервер нужен Mini App с холстом. Railway отдаёт порт в PORT.
    web_runner = None
    port = int(os.getenv("PORT", "0") or 0)

    if port:
        try:
            web_runner = await start_web_server(bot, TOKEN, port)
        except Exception as error:
            logger.error("WEB SERVER: %s %s", type(error).__name__, error)

    logger.info(
        "Крокодил: %s",
        "холст в Telegram" if drawing_enabled() else "словесный режим",
    )

    if drawing_enabled() and not public_url():
        logger.warning(
            "WEBAPP_SHORT_NAME задан, но PUBLIC_URL/RAILWAY_PUBLIC_DOMAIN пуст"
        )

    from settings.registry import FEATURES
    logger.info("Функций в реестре: %s", len(FEATURES))

    logger.info("МАРУСЬКА ЗАПУЩЕНА!")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        if web_runner is not None:
            await web_runner.cleanup()
        await bot.session.close()
        await close_db()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Маруська остановлена.")
