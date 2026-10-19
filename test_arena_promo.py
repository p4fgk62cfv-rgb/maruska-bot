"""
Арена в группе: расписание, один раз на слот, кнопка «Войти в игру».

    python test_arena_promo.py                      — без базы: только расписание
    TEST_DATABASE_URL=postgresql://… python test_arena_promo.py
"""

import asyncio
import os
import pathlib
import random
import sys
from datetime import datetime
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).parent))
DB_URL = os.getenv("TEST_DATABASE_URL", "")
os.environ.setdefault("DATABASE_URL", DB_URL or "postgresql+asyncpg://x:y@127.0.0.1:1/z")

import features.arena_promo as ap  # noqa: E402

errors = []


def check(ok, what):
    if not ok:
        errors.append(what)


def hours(start, every):
    return [h for h in range(24) if ap.slot_now(h, start, every)]


check(hours(10, 12) == [10, 22], f"два раза в день: {hours(10, 12)}")
check(hours(10, 4) == [10, 14, 18, 22], f"каждые 4 часа без ночи: {hours(10, 4)}")
check(hours(12, 12) == [12], f"12 и 24 → только 12 (полночь — ночь): {hours(12, 12)}")
check(hours(9, 24) == [9], "раз в сутки")
check(all(len(t) < 1000 and "Арен" in t for t in ap.TEXTS), "тексты про Арену")


async def database():
    from database.database import init_db
    from settings import store

    await init_db()
    os.environ["ARENA_APP_NAME"] = "play"
    chat = -100777000000 - random.randint(0, 10**6)
    sent = []

    async def send_message(chat_id, text, reply_markup=None):
        sent.append((chat_id, text, reply_markup))

    async def me():
        return SimpleNamespace(username="BotMaruska_bot")

    bot = SimpleNamespace(send_message=send_message, me=me)

    ap.local_now = lambda chat_id: datetime(2026, 10, 19, 10, 5)
    store.prime(chat, {})
    check(not await ap.check_chat(bot, chat), "выключено по умолчанию")

    store.prime(chat, {"arena_promo": True, "arena_promo_hours": 12, "arena_promo_hour": 10})
    check(await ap.check_chat(bot, chat), "10:05 — отправила")
    check(not await ap.check_chat(bot, chat), "в том же часу второй раз — нет")
    ap.local_now = lambda chat_id: datetime(2026, 10, 19, 13, 0)
    check(not await ap.check_chat(bot, chat), "13:00 — не по расписанию")
    ap.local_now = lambda chat_id: datetime(2026, 10, 19, 22, 30)
    check(await ap.check_chat(bot, chat), "22:30 — второй раз за день")
    check(len(sent) == 2 and all(c == chat for c, _, _ in sent), f"два сообщения: {len(sent)}")
    button = sent[0][2].inline_keyboard[0][0]
    check(button.text == "🎮 Войти в игру" and button.url == "https://t.me/BotMaruska_bot/play", f"кнопка: {button}")

    os.environ["ARENA_APP_NAME"] = ""
    ap.local_now = lambda chat_id: datetime(2026, 10, 20, 10, 0)
    check(not await ap.check_chat(bot, chat), "без мини-приложения не шлёт пустое")


if DB_URL:
    asyncio.run(database())
else:
    print("ℹ️  TEST_DATABASE_URL не задан — сценарий с базой пропущен")

if errors:
    print("❌ " + "\n❌ ".join(errors))
    sys.exit(1)
print("✅ Арена в группе: все проверки прошли.")
