"""
«Мара, инфа …» — вероятность случайным процентом.
Запуск:  python test_info_chance.py
"""

import asyncio
import os
import pathlib
import re
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).parent))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:y@127.0.0.1:1/z")

import botcontext  # noqa: E402
from features import info_chance as ic  # noqa: E402

errors = []
botcontext.BOT_ID = 777
ic.is_enabled = lambda chat_id, key: True

for text, want in [
    ("Мара инфа что Стас сегодня чокнулся", "Что Стас сегодня чокнулся"),
    ("Мара, инфа: Вася влюбился?", "Вася влюбился"),
    ("Маруся, инфа что завтра будет снег!", "Что завтра будет снег"),
    ("Мара инфа", ""),
    ("Мара, как дела", None),
    ("инфа что Стас чокнулся", None),
    ("Мара, информация о погоде", None),
    ("Мара, инфаркт это опасно?", None),
    ("/инфа что-то", None),
]:
    if ic.parse(text) != want:
        errors.append(f"{text!r}: {ic.parse(text)!r}, ждали {want!r}")

text = ic.answer("Что <Стас> сегодня чокнулся", 73)
if "Вероятность инфы: <b>Что &lt;Стас&gt; сегодня чокнулся</b>" not in text or "Составляет <b>73%</b>" not in text:
    errors.append(f"ответ: {text}")
for percent in (0, 10, 11, 50, 51, 90, 91, 100):
    if not ic.verdict(percent):
        errors.append(f"нет приписки для {percent}%")


async def main():
    said = []

    async def reply(t):
        said.append(t)

    seen = set()
    for _ in range(30):
        said.clear()
        m = types.SimpleNamespace(text="Мара инфа что Стас сегодня чокнулся", reply_to_message=None, reply=reply,
                                  chat=types.SimpleNamespace(id=-100, type="supergroup"),
                                  from_user=types.SimpleNamespace(id=1, is_bot=False))
        if not ic.is_info_question(m):
            errors.append("вопрос не распознан")
            return
        await ic.info_chance(m)
        found = re.search(r"Составляет <b>(\d+)%</b>", said[0])
        if not found or not 0 <= int(found.group(1)) <= 100:
            errors.append(f"процент: {said}")
            return
        seen.add(found.group(1))
    if len(seen) < 5:
        errors.append("процент не случайный")


asyncio.run(main())

if errors:
    print("❌ " + "\n❌ ".join(errors))
    sys.exit(1)
print("✅ «Мара, инфа»: все проверки прошли.")
