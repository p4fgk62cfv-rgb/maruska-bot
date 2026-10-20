"""
«Мара, кто сегодня …» — случайный участник группы.
Запуск:  python test_who_today.py
"""

import asyncio
import os
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).parent))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:y@127.0.0.1:1/z")

import botcontext  # noqa: E402
import database.repository as repo  # noqa: E402
from features import who_today as wt  # noqa: E402

errors = []
botcontext.BOT_ID = 777

for text, want in [
    ("Мара кто меня сегодня любит?", ("тебя любит", True)),
    ("Мара, кто сегодня злой зайка", ("злой зайка", False)),
    ("Мара кто сегодня улитка", ("улитка", False)),
    ("Мара кто сегодня моя зайка?", ("твоя зайка", True)),
    ("Маруся, кто у нас сегодня самый красивый в чате?", ("самый красивый", False)),
    ("Мара кто я?", None),
    ("Мара, кто Вася?", None),
    ("Мара, кто такой Пушкин", None),
    ("Мара что сегодня на обед", None),
    ("Мара кто сегодня", None),
    ("/кто сегодня улитка", None),
]:
    if wt.parse(text) != want:
        errors.append(f"{text!r}: {wt.parse(text)}, ждали {want}")

wt.is_enabled = lambda chat_id, key: True


async def me():
    return types.SimpleNamespace(id=777)


def msg(text, reply=None, kind="supergroup"):
    said = []

    async def answer(t):
        said.append(t)

    m = types.SimpleNamespace(
        text=text, reply_to_message=reply, reply=answer, bot=types.SimpleNamespace(me=me),
        chat=types.SimpleNamespace(id=-100, type=kind),
        from_user=types.SimpleNamespace(id=1, is_bot=False, first_name="Стас", username=None),
    )
    return m, said


async def main():
    people = [{"telegram_id": 1, "name": "Стас"}, {"telegram_id": 2, "name": "Катя"}, {"telegram_id": 777, "name": "Мара"}]

    async def candidates(chat_id, days):
        return people

    repo.pick_candidates = candidates

    m, said = msg("Мара кто сегодня улитка?")
    if not wt.is_who_question(m):
        errors.append("вопрос с именем Мары не распознан")
    m2, _ = msg("кто сегодня улитка?")
    if wt.is_who_question(m2):
        errors.append("без обращения к Маре не отвечаем")
    m3, _ = msg("Мара кто сегодня улитка?", kind="private")
    if wt.is_who_question(m3):
        errors.append("в личке выбирать некого")

    seen = set()
    for _ in range(40):
        m, said = msg("Мара кто сегодня улитка?")
        await wt.who_today(m)
        text = said[0]
        if "улитка" not in text or "id=777" in text:
            errors.append(f"ответ: {text}")
            break
        seen |= {uid for uid in ("id=1\"", "id=2\"") if uid in text}
    if seen != {"id=1\"", "id=2\""}:
        errors.append(f"выбирает случайно из всех, включая спросившего: {seen}")

    for _ in range(20):
        m, said = msg("Мара кто меня сегодня любит?")
        await wt.who_today(m)
        text = said[0]
        if "тебя любит" not in text or 'id=2"' not in text or text.count('id=1"') != 1:
            errors.append(f"«кто меня любит» — не сам спросивший: {text}")
            break

    people[:] = [{"telegram_id": 1, "name": "Стас"}]
    m, said = msg("Мара кто меня сегодня любит?")
    await wt.who_today(m)
    if "некого" not in said[0]:
        errors.append(f"некого выбрать: {said}")

    people[:] = [{"telegram_id": 2, "name": "<b>Хак</b>"}]
    m, said = msg("Мара кто сегодня улитка?")
    await wt.who_today(m)
    if "<b>Хак</b>" in said[0]:
        errors.append("имя не экранировано")


asyncio.run(main())

if errors:
    print("❌ " + "\n❌ ".join(errors))
    sys.exit(1)
print("✅ «Кто сегодня»: все проверки прошли.")
