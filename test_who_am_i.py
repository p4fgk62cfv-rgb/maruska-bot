"""
«Мара, кто я?» — характеристика по памяти Мары.
Запуск:  python test_who_am_i.py
"""

import asyncio
import os
import pathlib
import sys
import types
from datetime import datetime, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).parent))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:y@127.0.0.1:1/z")

import ai.router  # noqa: E402
import botcontext  # noqa: E402
import database.repository as repo  # noqa: E402
from features import who_am_i as w  # noqa: E402
from features import who_today  # noqa: E402

errors = []
botcontext.BOT_ID = 777
w.is_enabled = lambda chat_id, key: True
w.get_value = lambda chat_id, key: None

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

prompts = []


async def fake_ai(prompt, persona=None):
    prompts.append(prompt)
    return "Ты душа чата <и> любитель пива."


async def messages_of(chat_id, uid, limit):
    return {1: ["привет всем", "кто на пиво?", "/bonus", "пиво лучше вина", "люблю футбол"], 2: ["ок"]}.get(uid, [])


async def member(chat_id, uid):
    return types.SimpleNamespace(messages_count=120)


async def since(chat_id, uid):
    return {"joined_at": datetime.utcnow() - timedelta(days=40), "exact": True, "left_at": None, "name": "Стас"}


async def profile(uid):
    return types.SimpleNamespace(karma=7)


async def birthday(uid):
    return (15, 3)


async def marriage(chat_id, uid):
    return None


async def name_of(chat_id, uid):
    return {1: "Стас", 2: "Вася"}.get(uid, "Игрок")


async def by_username(username):
    return types.SimpleNamespace(telegram_id=2) if username.lower() == "vasya" else None


ai.router.ask_ai = fake_ai
repo.user_messages = messages_of
repo.get_member = member
repo.member_since = since
repo.get_profile = profile
repo.get_birthday = birthday
repo.active_marriage = marriage
repo.member_name = name_of
repo.get_user_by_username = by_username


async def main():
    m, said = msg("Мара, кто я?")
    await w.who_am_i(m)
    if not said or "душа чата" not in said[0] or "&lt;и&gt;" not in said[0]:
        errors.append(f"ответ нейросети (и экранирован): {said}")
    p = prompts[-1]
    for fact in ("пиво лучше вина", "120", "В группе дней: 40", "Карма", "15.03", "на «ты»"):
        if fact not in p:
            errors.append(f"в подсказке нет «{fact}»")
    if "/bonus" in p:
        errors.append("команды не попадают в память для характеристики")

    m, said = msg("Мара, кто это?", vasya)
    await w.who_am_i(m)
    if not said or "мало знаю" not in said[0] or "Вася" not in said[0]:
        errors.append(f"мало сообщений — честно говорит: {said}")

    m, said = msg("Мара кто @nobody?")
    await w.who_am_i(m)
    if not said or "Не знаю такого" not in said[0]:
        errors.append(f"неизвестный ник: {said}")

    async def broken_ai(prompt, persona=None):
        raise RuntimeError("все нейросети молчат")

    ai.router.ask_ai = broken_ai
    m, said = msg("Мара, кто я?")
    await w.who_am_i(m)
    if not said or "Маруська знает" not in said[0] or "120" not in said[0]:
        errors.append(f"без нейросети — факты: {said}")


asyncio.run(main())

if errors:
    print("❌ " + "\n❌ ".join(errors))
    sys.exit(1)
print("✅ «Мара, кто я?»: все проверки прошли.")
