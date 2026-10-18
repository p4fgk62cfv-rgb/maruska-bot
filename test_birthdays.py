"""
Дни рождения: даты, напоминания, подарок (раз в год), список.

    python test_birthdays.py                      — без базы: только чистые функции
    TEST_DATABASE_URL=postgresql://… python test_birthdays.py
"""

import asyncio
import os
import pathlib
import sys
from datetime import date, datetime
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).parent))
DB_URL = os.getenv("TEST_DATABASE_URL", "")
os.environ.setdefault("DATABASE_URL", DB_URL or "postgresql+asyncpg://x:y@127.0.0.1:1/z")

import features.birthdays as bd  # noqa: E402

errors, checks = [], 0


def check(ok, what):
    global checks
    checks += 1
    if not ok:
        errors.append(what)


for text, want in [("15.03", (15, 3)), ("15/3", (15, 3)), ("1-12", (1, 12)), ("15.03.1990", (15, 3)),
                   ("15 марта", (15, 3)), ("15 мар", (15, 3)), ("29.02", (29, 2)), ("31 декабря 1999", (31, 12)),
                   ("31.04", None), ("32.01", None), ("15.13", None), ("завтра", None), ("", None)]:
    check(bd.parse_date(text) == want, f"дата «{text}» → {bd.parse_date(text)}, ждали {want}")

today = date(2026, 10, 19)
check(bd.days_until(19, 10, today) == 0, "сегодня")
check(bd.days_until(21, 10, today) == 2, "послезавтра")
check(bd.days_until(18, 10, today) == 364, "вчера — через год")
check(bd.days_until(1, 1, date(2026, 12, 31)) == 1, "через Новый год")
check(bd.days_until(29, 2, date(2027, 2, 27)) == 1, "29 февраля в невисокосный — 28-го")

check(bd.due_kinds(0, 2) == ["d0"] and bd.due_kinds(2, 2) == ["d2"] and bd.due_kinds(1, 2) == ["d1"], "что пора отправить")
check(bd.due_kinds(2, 1) == [] and bd.due_kinds(1, 0) == [] and bd.due_kinds(3, 3) == ["d3"], "напоминать заранее — по настройке")

listing = bd.format_list([{"name": "Катя", "day": 21, "month": 10}, {"name": "<b>", "day": 19, "month": 10}], today)
check("Катя</b> — послезавтра" in listing and "&lt;b&gt;" in listing and listing.index("&lt;b&gt;") < listing.index("Катя"),
      f"список: {listing}")
check("ещё никто" in bd.format_list([], today), "пустой список")

text = bd.reminder_text("d0", "<a>Катя</a>", 500)
check("Сегодня день рождения" in text and "500 💎" in text, f"поздравление: {text}")
check("💎" not in bd.reminder_text("d0", "Катя", 0), "без подарка — без алмазов")
check(len(bd.days_keyboard(1, 2).inline_keyboard) == 6, "в феврале 29 дней кнопками")


async def database():
    import random

    from database.database import init_db
    from database.repository import (
        birthday_ask_state, chat_birthdays, ensure_member, get_birthday, get_profile,
        mark_birthday_asked, mark_member_left, set_birthday,
    )
    from settings import store

    await init_db()
    chat = -100555000000 - random.randint(0, 10**6)
    kate, vasya, gone = (random.randint(10**9, 2 * 10**9) for _ in range(3))
    for uid, name in ((kate, "Катя"), (vasya, "Вася"), (gone, "Ушедший")):
        await ensure_member(chat, uid, name)
    await mark_member_left(chat, gone, True)

    await set_birthday(kate, 19, 10)        # сегодня
    await set_birthday(vasya, 21, 10)       # послезавтра
    await set_birthday(gone, 19, 10)
    await set_birthday(vasya, 21, 10)       # повтор — без ошибки
    check(await get_birthday(kate) == (19, 10), "дата сохранена")
    check({p["telegram_id"] for p in await chat_birthdays(chat)} == {kate, vasya}, "вышедших не поздравляем")

    check(await birthday_ask_state(kate) is None, "ещё не спрашивали")
    await mark_birthday_asked(kate, declined=True)
    check((await birthday_ask_state(kate))["declined"], "«не скажу» запомнено")

    store.prime(chat, {"birthday_gift": 300, "birthday_hour": 10, "birthday_remind_days": 2})
    before = (await get_profile(kate)).coins if await get_profile(kate) else 0

    sent = []
    fake_bot = SimpleNamespace(send_message=lambda chat_id, text, **_: _record(sent, text))
    bd.local_now = lambda chat_id: datetime(2026, 10, 19, 9)          # до часа поздравлений
    check(await bd.run_reminders(fake_bot, chat) == 0, "до 10:00 — тишина")
    bd.local_now = lambda chat_id: datetime(2026, 10, 19, 12)
    first = await bd.run_reminders(fake_bot, chat)
    second = await bd.run_reminders(fake_bot, chat)
    check(first == 2 and second == 0, f"поздравление Кате и напоминание о Васе — один раз: {first}, {second}, {sent}")
    check(any("Сегодня день рождения" in t and "300 💎" in t for t in sent), "поздравление с подарком")
    check(any("Послезавтра" in t for t in sent), "напоминание за 2 дня")
    check((await get_profile(kate)).coins - before == 300, "300 алмазов начислены")

    # Та же Катя во второй группе: поздравление есть, второго подарка нет
    other = chat - 1
    await ensure_member(other, kate, "Катя")
    store.prime(other, {"birthday_gift": 300})
    sent.clear()
    await bd.run_reminders(fake_bot, other)
    check(sent and "💎" not in sent[0] and (await get_profile(kate)).coins - before == 300,
          f"подарок один раз в год на человека: {sent}")

    store.prime(chat - 2, {"birthdays": False})
    await ensure_member(chat - 2, kate, "Катя")
    check(await bd.run_reminders(fake_bot, chat - 2) == 0, "выключено в группе — молчим")


async def _record(sent, text):
    sent.append(text)


if DB_URL:
    asyncio.run(database())
else:
    print("   (без TEST_DATABASE_URL база не проверялась)")

if errors:
    print(f"❌ {len(errors)} из {checks} проверок не прошли:")
    print("\n".join("  " + e for e in errors))
    sys.exit(1)

print(f"✅ Все {checks} проверок дней рождения прошли.")
