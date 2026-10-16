"""
«Мара, нарисуй …»: распознавание просьбы, лимиты, Gemini и запасной художник.
Сеть не нужна. Запуск:  python test_draw.py
"""

import asyncio
import os
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).parent))
os.environ.setdefault("GEMINI_API_KEY", "test")

import botcontext  # noqa: E402
import features.draw as d  # noqa: E402
import ai.images as images  # noqa: E402

errors = []


def check(ok, what):
    if not ok:
        errors.append(what)


botcontext.BOT_ID = 999


def msg(text, chat_id=-100, reply_to_bot=False):
    reply = types.SimpleNamespace(from_user=types.SimpleNamespace(id=999)) if reply_to_bot else None
    return types.SimpleNamespace(text=text, chat=types.SimpleNamespace(id=chat_id, type="private" if chat_id > 0 else "supergroup"),
                                 reply_to_message=reply)


CASES = {
    "Мара, нарисуй кота в шляпе": "кота в шляпе",
    "Маруська нарисуй-ка закат над морем": "закат над морем",
    "мара: нарисуй: дракона": "дракона",
    "Мара, сделай картинку пиццы": "пиццы",
    "Мара изобрази Стаса королём": "Стаса королём",
    "Мара, нарисуй": "",
}
for text, want in CASES.items():
    check(d.draw_request(msg(text)) == want, f"{text!r} → {d.draw_request(msg(text))!r}")
check(d.draw_request(msg("нарисуй луну", reply_to_bot=True)) == "луну", "ответом на сообщение Мары")
check(d.draw_request(msg("нарисуй луну", chat_id=5)) == "луну", "в личке без имени")
for text in ("нарисуй кота", "Мара, как дела?", "я вчера рисовал кота, Мара", "Марат, нарисуй", "/draw кот"):
    check(d.draw_request(msg(text)) is None, f"лишнее срабатывание: {text!r}")

# Лимиты
d.get_number = lambda chat, key: 2
check(d.limit_problem(-1, 1) is None, "первый рисунок можно")
d.note(-1, 1)
check("кисточке" in (d.limit_problem(-1, 1) or ""), "пауза для одного человека")
d.note(-1, 2)
check("лимит" in (d.limit_problem(-1, 3) or ""), "суточный лимит группы")


async def main():
    calls = []

    async def gemini_ok(prompt):
        calls.append("gemini")
        return b"PNG"

    async def gemini_quota(prompt):
        calls.append("gemini")
        raise RuntimeError("429 RESOURCE_EXHAUSTED: quota for image generation is 0 on free tier")

    async def gemini_refuse(prompt):
        raise images.DrawRefused("safety")

    async def free(prompt):
        calls.append("free")
        return b"JPG"

    images.free_draw = free

    images.gemini_draw = gemini_ok
    check(await images.draw("кот") == (b"PNG", "Gemini"), "рисует Gemini")

    images.gemini_draw = gemini_quota
    check(await images.draw("кот") == (b"JPG", "Pollinations"), "лимит → запасной художник")
    n = calls.count("gemini")
    check(await images.draw("кот") == (b"JPG", "Pollinations") and calls.count("gemini") == n, "на паузе Gemini не дёргаем")

    images._paused_until = 0
    images.gemini_draw = gemini_refuse
    try:
        await images.draw("что-то запрещённое")
        check(False, "отказ фильтра должен дойти до пользователя")
    except images.DrawRefused:
        pass


asyncio.run(main())

if errors:
    print("❌ " + "\n❌ ".join(errors))
    sys.exit(1)
print("✅ Рисунки Мары: просьбы, лимиты и запасной художник работают.")
