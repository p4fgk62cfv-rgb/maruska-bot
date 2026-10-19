"""
Игры в группе: расписание, случайная минута, один раз на слот,
кнопки «Арена» и «Рыбалка», команда /arena.

    python test_arena_promo.py                      — без базы: расписание и команда
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
from fishing import service as fishing_service  # noqa: E402
from webapp import server  # noqa: E402

errors = []


def check(ok, what):
    if not ok:
        errors.append(what)


def hours(start, every):
    return [h for h in range(24) if ap.slot_now(h, start, every)]


check(hours(10, 4) == [10, 14, 18, 22], f"каждые 4 часа без ночи: {hours(10, 4)}")
check(hours(10, 12) == [10, 22], f"два раза в день: {hours(10, 12)}")
check(hours(12, 12) == [12], f"12 и 24 → только 12 (полночь — ночь): {hours(12, 12)}")
minutes = {ap.slot_minute(-100, "2026-10-19", h) for h in range(24)}
check(all(0 <= m < 50 for m in minutes) and len(minutes) > 5, f"минута случайная: {minutes}")
check(ap.slot_minute(-100, "2026-10-19", 10) == ap.slot_minute(-100, "2026-10-19", 10), "минута постоянна для слота")
check(all(len(t) < 1500 and "Арена" in t and "Рыбалка" in t for t in ap.TEXTS), "тексты про Арену и Рыбалку")

os.environ["ARENA_APP_NAME"] = "play"
os.environ["ARENA_URL"] = "https://arena.example"
server.public_url = lambda: "https://bot.example"
fishing_service.settings = lambda: {"enabled": True}
ap.is_enabled = lambda chat_id, key: True

sent, replies = [], []


async def send_message(chat_id, text, reply_markup=None):
    sent.append((chat_id, text, [b for row in reply_markup.inline_keyboard for b in row]))


async def me():
    return SimpleNamespace(username="BotMaruska_bot")


bot = SimpleNamespace(send_message=send_message, me=me)


async def reply(text):
    replies.append(text)


def msg(text, chat_id=-100123, kind="supergroup"):
    return SimpleNamespace(text=text, reply_to_message=None, bot=bot, reply=reply,
                           chat=SimpleNamespace(id=chat_id, type=kind))


async def command():
    check(ap.is_open_request(msg("Арена")) and ap.is_open_request(msg("мара, арена")), "«арена» открывает")
    check(not ap.is_open_request(msg("пошли на арену вечером")), "в середине фразы — нет")
    await ap.arena_promo_command(msg("/arena"))
    await ap.arena_promo_command(msg("/arena"))
    check(len(sent) == 1, f"группа: одно сообщение за минуту: {len(sent)}")
    buttons = sent[0][2]
    check([b.text for b in buttons] == ["🃏 Арена — дурак онлайн", "🎣 Рыбалка"], f"две кнопки: {[b.text for b in buttons]}")
    check(buttons[0].url == "https://t.me/BotMaruska_bot/play"
          and buttons[1].url.startswith("https://t.me/BotMaruska_bot/fishing?startapp=g"), "в группе — ссылки t.me")
    await ap.arena_promo_command(msg("/arena", chat_id=5, kind="private"))
    check(len(sent) == 2 and all(b.web_app for b in sent[1][2]), "в личке — кнопки web_app")

    os.environ["ARENA_APP_NAME"] = ""
    await ap.arena_promo_command(msg("/arena", chat_id=-100555))
    check([b.text for b in sent[-1][2]] == ["🎣 Рыбалка"], "без Арены — только Рыбалка")
    fishing_service.settings = lambda: {"enabled": False}
    await ap.arena_promo_command(msg("/arena", chat_id=-100999))
    check(replies and "скоро откроются" in replies[0], "без игр — объяснение")
    os.environ["ARENA_APP_NAME"] = "play"
    fishing_service.settings = lambda: {"enabled": True}


asyncio.run(command())


async def database():
    from database.database import init_db
    from settings import store

    await init_db()
    ap.is_enabled = store.is_enabled
    chat = -100777000000 - random.randint(0, 10**6)
    sent.clear()
    store.prime(chat, {})
    minute = ap.slot_minute(chat, "2026-10-19", 10)

    ap.local_now = lambda chat_id: datetime(2026, 10, 19, 10, 59)
    check(not await ap.check_chat(bot, chat), "выключено по умолчанию")

    store.prime(chat, {"arena_promo": True, "fishing": True})
    if minute:
        ap.local_now = lambda chat_id: datetime(2026, 10, 19, 10, minute - 1)
        check(not await ap.check_chat(bot, chat), "до своей минуты — ждёт")
    ap.local_now = lambda chat_id: datetime(2026, 10, 19, 10, 59)
    check(await ap.check_chat(bot, chat), "10:59 — отправила (по умолчанию каждые 4 с 10)")
    check(not await ap.check_chat(bot, chat), "в том же часу второй раз — нет")
    ap.local_now = lambda chat_id: datetime(2026, 10, 19, 12, 59)
    check(not await ap.check_chat(bot, chat), "12:59 — не по расписанию")
    ap.local_now = lambda chat_id: datetime(2026, 10, 19, 14, 59)
    check(await ap.check_chat(bot, chat), "14:59 — следующий слот")
    ap.local_now = lambda chat_id: datetime(2026, 10, 20, 2, 59)
    check(not await ap.check_chat(bot, chat), "ночью — нет")
    check(len(sent) == 2 and all(len(b) == 2 for _, _, b in sent), f"два сообщения с двумя кнопками: {len(sent)}")


if DB_URL:
    asyncio.run(database())
else:
    print("ℹ️  TEST_DATABASE_URL не задан — сценарий с базой пропущен")

if errors:
    print("❌ " + "\n❌ ".join(errors))
    sys.exit(1)
print("✅ Игры в группе: все проверки прошли.")
