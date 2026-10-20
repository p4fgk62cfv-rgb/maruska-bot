"""
«Мара, кто я?» — карточка человека (как /profile), у каждого своя.
Запуск:  python test_who_am_i.py
"""

import asyncio
import os
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).parent))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:y@127.0.0.1:1/z")

import botcontext  # noqa: E402
from features import who_am_i as w  # noqa: E402
from features import who_today  # noqa: E402

errors = []
botcontext.BOT_ID = 777

vasya = types.SimpleNamespace(id=2, is_bot=False, first_name="Вася", username="vasya")


def msg(text, reply_user=None, uid=1):
    said = []

    async def reply(t):
        said.append(t)

    async def action(*a):
        pass

    m = types.SimpleNamespace(
        text=text, reply=reply,
        reply_to_message=types.SimpleNamespace(from_user=reply_user) if reply_user else None,
        bot=types.SimpleNamespace(send_chat_action=action),
        chat=types.SimpleNamespace(id=-100, type="supergroup"),
        from_user=types.SimpleNamespace(id=uid, is_bot=False, first_name="Стас", username="stas"),
    )
    return m, said


for text, reply_user, want in [
    ("Мара, кто я?", None, ("me", None)),
    ("Мара кто я такой", None, ("me", None)),
    ("Маруся, что ты обо мне знаешь?", None, ("me", None)),
    ("Мара, расскажи обо мне", None, ("me", None)),
    ("Мара кто @vasya?", None, ("mention", "vasya")),
    ("Мара, кто это?", vasya, ("reply", None)),
    ("Мара, кто это?", None, None),
    ("Мара, кто я сегодня?", None, None),
    ("Мара, кто такой Пушкин", None, None),
    ("кто я?", None, ("me", None)),
]:
    m, _ = msg(text, reply_user)
    if w.parse(m) != want:
        errors.append(f"{text!r}: {w.parse(m)}, ждали {want}")

m, _ = msg("кто я?")
if w.is_who_am_i(m):
    errors.append("без обращения к Маре не отвечаем")
m, _ = msg("Мара, кто я сегодня?")
if w.is_who_am_i(m) or who_today.parse(m.text) is None:
    errors.append("«кто я сегодня» — это «кто сегодня», не характеристика")

from features import rating  # noqa: E402
from features import social  # noqa: E402
import database.repository as repo  # noqa: E402

PROFILES = {
    1: dict(display_name="STANISLAV", karma=26, xp=2125, bonus_streak=1, messages_count=1042, games_played=26, games_won=10),
    2: dict(display_name="Вася", karma=3, xp=10, bonus_streak=0, messages_count=7, games_played=0, games_won=0),
}


async def get_profile(uid):
    data = PROFILES.get(uid)
    return types.SimpleNamespace(**data) if data else None


async def created(telegram_id, display_name=None):
    PROFILES[telegram_id] = dict(display_name=display_name, karma=0, xp=0, bonus_streak=0,
                                 messages_count=0, games_played=0, games_won=0)


async def position(uid):
    return 1 if uid == 1 else 5


async def stats(uid):
    return {"positive": 16 if uid == 1 else 0, "negative": 0}


async def balance(uid):
    return 1287 if uid == 1 else 0


async def inventory(uid):
    return 0


async def marriage(chat_id, uid):
    return "💍 В браке с <b>Lesya</b> — 25 дней" if uid == 1 else None


async def by_username(username):
    return types.SimpleNamespace(telegram_id=2) if username.lower() == "vasya" else None


async def name_of(chat_id, uid):
    return {1: "Стас", 2: "Вася"}.get(uid, "Игрок")


rating.is_enabled = lambda chat_id, key: True
rating.get_profile = get_profile
rating.create_profile_if_needed = created
rating.get_rating_position = position
rating.get_rating_stats = stats
rating.get_balance = balance
rating.count_inventory = inventory
social.marriage_line = marriage
repo.get_user_by_username = by_username
repo.member_name = name_of


async def main():
    m, said = msg("Мара, кто я?")
    await w.who_am_i(m)
    card = said[0] if said else ""
    for part in ("👤 <b>STANISLAV</b>", "💍 В браке с <b>Lesya</b> — 25 дней", "Рейтинг: <b>26</b>", "Место: <b>#1</b>",
                 "1 287", "Серия бонусов: <b>1</b>", "Сообщений: <b>1042</b>", "Игр: <b>26</b>", "Побед: <b>10</b>",
                 "Положительных оценок: <b>16</b>"):
        if part not in card:
            errors.append(f"«кто я» — в карточке нет {part!r}")

    m, said = msg("Мара, кто это?", vasya)
    await w.who_am_i(m)
    if not said or "👤 <b>Вася</b>" not in said[0] or "В браке" in said[0]:
        errors.append(f"«кто это» ответом — карточка Васи: {said}")

    m, said = msg("Мара кто @vasya?")
    await w.who_am_i(m)
    if not said or "👤 <b>Вася</b>" not in said[0]:
        errors.append(f"«кто @vasya» — карточка Васи: {said}")

    m, said = msg("Мара кто @nobody?")
    await w.who_am_i(m)
    if not said or "Не знаю такого" not in said[0]:
        errors.append(f"неизвестный ник: {said}")

    # Новичок без профиля — карточка создаётся
    m, said = msg("Мара, кто я?", uid=3)
    await w.who_am_i(m)
    if not said or "👤 <b>Стас</b>" not in said[0]:
        errors.append(f"новичок — своя карточка: {said}")

    # /profile — та же карточка
    answered = []

    async def answer(t):
        answered.append(t)

    m, _ = msg("/profile")
    m.answer = answer
    await rating.profile_handler(m)
    if not answered or "👤 <b>STANISLAV</b>" not in answered[0]:
        errors.append(f"/profile: {answered}")


asyncio.run(main())

if errors:
    print("❌ " + "\n❌ ".join(errors))
    sys.exit(1)
print("✅ «Мара, кто я?»: все проверки прошли.")
