"""
Мара — точка входа.

Здесь только запуск: конфигурация, порядок роутеров, поднятие
веб-сервера и фоновых задач. Вся логика живёт в модулях:

    features/   — разговор, рейтинг, погода, котики, предсказания,
                  приветствие, итоги недели
    actions/    — 205 действий с картинками
    games/      — крокодил, кубики
    economy/    — алмазы, магазин, подарки
    progress/   — опыт, уровни, достижения
    settings/   — админ-панель и реестр функций
    webapp/     — холст крокодила как Mini App
"""

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import logging_setup

from botcontext import set_identity

from database.database import close_db, init_db
from database.repository import backfill_daily_stats

from actions.handler import router as actions_router
from actions.providers import available_providers

from economy.handler import router as economy_router
from economy.shop_handler import router as shop_router

from features.basic import router as basic_router
from features.cats import router as cats_router
from features.chat import router as chat_router, set_context_size
from features.digest import digest_loop, router as digest_router
from features.fortune import router as fortune_router
from features.greeting import router as greeting_router
from features.automod import router as automod_router
from features.captcha import router as captcha_router
from images_library import router as library_router
from features.autoreplies import router as autoreplies_router
from features.moderation import router as moderation_router
from features.rating import router as rating_router
from features.weather import router as weather_router

from games.crocodile import (
    drawing_enabled,
    restore_rounds,
    router as crocodile_router,
    set_bot_username,
)
from games.dice import router as dice_router

from progress.handler import router as progress_router

from settings.handler import (
    router as settings_router,
    set_bot_username as set_settings_username,
)
from settings.middleware import SettingsMiddleware, StatsMiddleware
from settings.registry import CHOICES, FEATURES

from webapp.server import public_url, start_web_server


logging_setup.setup()

logger = logging.getLogger("maruska")


# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

CONTEXT_MESSAGES = int(os.getenv("CONTEXT_MESSAGES", "8"))


bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

dp = Dispatcher()


# =========================================================
# ROUTERS
# =========================================================
#
# Порядок важен. Сверху — то, что должно перехватывать
# сообщение раньше остальных, снизу — самый общий обработчик.
#
# =========================================================

# Настройки читаются до фильтров, иначе выключенные функции
# успеют сработать.
dp.message.outer_middleware(SettingsMiddleware())
dp.callback_query.outer_middleware(SettingsMiddleware())

# Статистика для графиков — до роутеров, чтобы видеть все сообщения
dp.message.outer_middleware(StatsMiddleware())

# Панель первой: /settings должен работать, даже если всё выключено
dp.include_router(settings_router)

# Служебные события чата
dp.include_router(greeting_router)

# Автомодерация раньше всего остального: нарушение удаляется
# до того, как на него отреагируют действия или разговор
dp.include_router(automod_router)
dp.include_router(captcha_router)

# Своя коллекция: фото владельца в личке с #тегом
dp.include_router(library_router)

# Команды
dp.include_router(basic_router)
dp.include_router(moderation_router)
dp.include_router(economy_router)
dp.include_router(shop_router)
dp.include_router(progress_router)
dp.include_router(digest_router)
dp.include_router(dice_router)
dp.include_router(rating_router)
dp.include_router(weather_router)
dp.include_router(cats_router)
dp.include_router(fortune_router)

# Игра раньше действий: во время раунда верная отгадка должна
# перехватываться первой
dp.include_router(crocodile_router)
dp.include_router(actions_router)

# Автоответы — после действий и до разговора с Марой:
# сработал автоответ — Gemini не тратится
dp.include_router(autoreplies_router)

# Самый общий обработчик — всегда последним
dp.include_router(chat_router)


# =========================================================
# СРОК ХРАНЕНИЯ ПАМЯТИ
# =========================================================

async def memory_loop():
    """
    Раз в 6 часов удаляет из памяти сообщения старше срока,
    заданного в каждой группе («Память: срок хранения»).
    """
    from database.repository import expire_memory, get_group_settings, memory_chat_ids
    from settings import store

    while True:
        try:
            await asyncio.sleep(6 * 3600)

            for chat_id in await memory_chat_ids():
                if chat_id >= 0:
                    continue

                if not store.is_loaded(chat_id):
                    try:
                        store.prime(chat_id, await get_group_settings(chat_id))
                    except Exception:
                        continue

                removed = await expire_memory(chat_id, store.get_number(chat_id, "memory_days") or 30)

                if removed:
                    logger.info("Память %s: удалено старых сообщений %s", chat_id, removed)

        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.error("MEMORY LOOP: %s %s", type(error).__name__, error)


# =========================================================
# ПРОВЕРКА ЛИШНИХ ФАЙЛОВ
# =========================================================
#
# Если при заливке файл попал не в ту папку, работает его старая
# копия из правильного места, а новая просто лежит мёртвым грузом.
# Так уже было с draw.html в корне. Бот проверяет это сам при старте.
#
# =========================================================

STRAY_FILES = {
    "draw.html": "webapp/static/draw.html",
    "admin.html": "webapp/static/admin.html",
    "crocodile.py": "games/crocodile.py",
    "words.py": "games/words.py",
    "state.py": "games/state.py",
    "database.py": "database/database.py",
    "models.py": "database/models.py",
    "repository.py": "database/repository.py",
    "handler.py": "папку actions/, settings/ или economy/",
    "server.py": "webapp/server.py",
    "registry.py": "settings/registry.py",
}


def check_stray_files() -> list[str]:
    from pathlib import Path

    root = Path(__file__).parent
    found = []

    for name, proper in STRAY_FILES.items():
        if (root / name).exists():
            found.append(f"{name} лежит в корне — должен быть в {proper}")

    return found


# =========================================================
# MAIN
# =========================================================

async def main():
    logger.info("МАРА ЗАПУСКАЕТСЯ...")

    for problem in check_stray_files():
        logger.warning("ЛИШНИЙ ФАЙЛ: %s", problem)

    set_context_size(CONTEXT_MESSAGES)

    await init_db()

    me = await bot.get_me()
    set_identity(me.id, me.username or "")
    set_bot_username(me.username or "")
    set_settings_username(me.username or "")

    logger.info("Бот: @%s (id=%s)", me.username, me.id)
    logger.info("PostgreSQL: подключён")
    logger.info("Gemini: подключён")

    providers = available_providers()
    logger.info(
        "Картинки: %s",
        ", ".join(providers) if providers else "личная библиотека / Telegram-кэш (внешние источники выключены)",
    )

    try:
        filled = await backfill_daily_stats()
        if filled:
            logger.info("История графиков восстановлена: %s дней", filled)
    except Exception as error:
        logger.warning("BACKFILL: %s %s", type(error).__name__, error)

    # Привязки своей коллекции картинок к действиям
    try:
        import images_library

        await images_library.reload_links()
        await images_library.reload_collections()
    except Exception as error:
        logger.warning("LIBRARY LINKS: %s", error)

    # Порядок источников картинок, заданный владельцем в панели
    try:
        from actions.providers import set_provider_order
        from database.repository import get_group_settings

        set_provider_order((await get_group_settings(0)).get("provider_order"))
    except Exception as error:
        logger.warning("PROVIDER ORDER: %s", error)

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

    logger.info(
        "Настроек: %s переключателей и %s списков",
        len(FEATURES),
        len(CHOICES),
    )

    digest_task = asyncio.create_task(digest_loop(bot))

    from webapp.admin_v2 import broadcast_loop

    broadcast_task = asyncio.create_task(broadcast_loop(bot))
    memory_task = asyncio.create_task(memory_loop())

    logger.info("МАРА ЗАПУЩЕНА!")

    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
        )
    finally:
        digest_task.cancel()
        broadcast_task.cancel()
        memory_task.cancel()

        if web_runner is not None:
            await web_runner.cleanup()

        await bot.session.close()
        await close_db()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Мара остановлена.")
