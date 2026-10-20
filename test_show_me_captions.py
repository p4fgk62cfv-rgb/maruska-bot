"""
«Мара, покажи меня»: подписей много, и недавние не повторяются.
Запуск:  python test_show_me_captions.py
"""

import asyncio
import os
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).parent))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:y@127.0.0.1:1/z")

from actions.show_me import CAPTIONS, MONKEY_CAPTIONS, RECENT_CAPTIONS, is_show_other, pick_caption, shown_name  # noqa: E402

errors = []


def check(name, ok):
    print(("OK   " if ok else "FAIL ") + name)
    if not ok:
        errors.append(name)


check("подписей не меньше 60", len(CAPTIONS) >= 60)
check("подписи без дублей", len(set(CAPTIONS)) == len(CAPTIONS))
check("в каждой подписи есть имя", all("{name}" in c for c in CAPTIONS))
check("без «(а)»", not any("(а)" in c for c in CAPTIONS))

picked = [pick_caption("Вася") for _ in range(RECENT_CAPTIONS + 1)]
check("подряд без повторов", len(set(picked)) == len(picked))
check("имя подставлено", all("Вася" in p for p in picked))

# «Мара, покажи Юлю» — без @ника и без ответа
NAMES = {
    "Мара, покажи Юлю": "Юля",
    "мара покажи машу": "Маша",
    "Мара покажи Ивана": "Иван",
    "Мара, покажи Андрея!": "Андрей",
    "Мара покажи Игоря": "Игорь",
    "Мара покажи Юлю Петрову": "Юля Петрова",
    "Мара покажи котика": None,
    "Мара покажи меня": None,
    "Мара, покажи погоду в Москве": None,
    "Мара покажи что умеешь": None,
    "Мара покажи его": None,
}
for text, expected in NAMES.items():
    check(f"{text} → {expected}", shown_name(text) == expected)
check("«покажи Юлю» без цели — это показ", is_show_other("Мара, покажи Юлю", has_target=False))
check("«покажи котика» без цели — нет", not is_show_other("Мара, покажи котика", has_target=False))

check("обезьяньих подписей не меньше 30", len(MONKEY_CAPTIONS) >= 30)
check("обезьяньи с именем и 🐒", all("{name}" in c and c.startswith("🐒") for c in MONKEY_CAPTIONS))
check("обезьянья подпись", pick_caption("Вася", monkey=True).startswith("🐒"))

# send_portrait: обезьянка из #обезьяна — с обезьяньей подписью, иначе котик
import images_library  # noqa: E402
from features import cats  # noqa: E402


class FakeMessage:
    chat = types.SimpleNamespace(id=-100)

    def __init__(self):
        self.photos = []

    async def answer_photo(self, photo, caption):
        self.photos.append((photo, caption))


async def run_portrait(tags, chance):
    message = FakeMessage()
    asked = []
    sent_cat = []

    async def fake_tags():
        return tags

    async def fake_pick(chat_id, target):
        asked.append(target)
        return {"file_id": "monkey-file"}

    async def fake_cat(msg, caption):
        sent_cat.append(caption)

    cats.monkey_tags, images_library.pick, cats.send_cat = fake_tags, fake_pick, fake_cat
    cats.MONKEY_CHANCE = chance
    await cats.send_portrait(message, "Вася")
    return message.photos, asked, sent_cat


photos, asked, sent_cat = asyncio.run(run_portrait(["обезьяна"], 1.0))
check("обезьянка из #обезьяна", asked == ["lib:обезьяна"] and photos and photos[0][0] == "monkey-file")
check("под обезьянкой обезьянья подпись", photos and photos[0][1].startswith("🐒") and not sent_cat)

photos, asked, sent_cat = asyncio.run(run_portrait(["обезьяна"], 0.0))
check("иначе котик с кошачьей подписью", not photos and sent_cat and sent_cat[0].startswith("🐱"))

photos, asked, sent_cat = asyncio.run(run_portrait([], 1.0))
check("нет коллекции обезьян — котик", not asked and sent_cat and sent_cat[0].startswith("🐱"))

if errors:
    sys.exit(1)
print("Всё ок")
