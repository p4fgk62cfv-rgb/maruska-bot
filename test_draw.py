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

REAL_CHECK = images.image_is_unsafe

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
    verdict = {"v": False}

    async def ok(name, result):
        async def f(prompt, safe):
            calls.append(name)
            return result
        return f

    async def quota(prompt, safe):
        calls.append("gemini")
        raise RuntimeError("429 RESOURCE_EXHAUSTED: You exceeded your current quota")

    async def check_img(data):
        return verdict["v"]

    images.image_is_unsafe = check_img
    images.DRAWERS["pollinations"] = await ok("pollinations", b"JPG")
    images.DRAWERS["huggingface"] = await ok("huggingface", b"HF")
    images.DRAWERS["gemini"] = await ok("gemini", b"PNG")
    os.environ["HF_TOKEN"] = "x"

    check(await images.draw("кот", primary="gemini") == (b"PNG", "Gemini"), "основной Gemini")
    check(await images.draw("кот", primary="pollinations") == (b"JPG", "Pollinations"), "основной Pollinations")
    check(await images.draw("кот", primary="gemini", enabled={"huggingface"}) == (b"HF", "Hugging Face"), "только включённый")

    images.DRAWERS["gemini"] = quota
    check(await images.draw("кот", primary="gemini") == (b"JPG", "Pollinations"), "лимит Gemini → следующий включённый")
    n = calls.count("gemini")
    await images.draw("кот", primary="gemini")
    check(calls.count("gemini") == n, "на паузе Gemini не дёргаем")

    try:
        await images.draw("кот", primary="gemini", enabled={"gemini"})
        check(False, "некому рисовать — NoArtist")
    except images.NoArtist:
        pass

    # Защита 18+: запрос и готовая картинка
    for bad in ("голая девушка", "девушка в бикини", "эротичная поза", "nude woman", "сиськи"):
        check(images.unsafe_prompt(bad), f"не отсеян запрос: {bad}")
    for fine in ("кот в шляпе", "голубое небо", "грузовик на мосту", "попугай", "членистоногие"):
        check(not images.unsafe_prompt(fine), f"зря отсеян: {fine}")
    try:
        await images.draw("голая девушка")
        check(False, "откровенный запрос не должен рисоваться")
    except images.DrawRefused:
        pass
    verdict["v"] = True
    try:
        await images.draw("кот", primary="pollinations")
        check(False, "картинка 18+ не должна показываться")
    except images.DrawRefused:
        pass
    check(await images.draw("кот", primary="pollinations", safe=False) == (b"JPG", "Pollinations"), "без защиты проверки нет")
    verdict["v"] = None
    try:
        await images.draw("кот", primary="pollinations")
        check(False, "без проверки картинку показывать нельзя")
    except images.DrawUnchecked:
        pass
    verdict["v"] = False

    # Без ключа Hugging Face пропускается
    os.environ.pop("HF_TOKEN")
    check(await images.draw("кот", primary="huggingface") == (b"JPG", "Pollinations"), "нет ключа HF — следующий")


asyncio.run(main())


# Художнику уходит только сам запрос — без «одеты», «no nudity» и т. п.
async def prompt_sent():
    import httpx

    sent = []

    async def tr(p):
        return "Flag of France"

    images.translate = tr

    def h(req):
        sent.append(str(req.url))
        return httpx.Response(200, content=b"\xff\xd8x", headers={"content-type": "image/jpeg"})

    real = httpx.AsyncClient
    images.httpx.AsyncClient = lambda **kw: real(transport=httpx.MockTransport(h), **kw)
    await images.pollinations_draw("флаг Франции", True)
    images.httpx.AsyncClient = real
    url = sent[0].lower()
    for bad in ("clothed", "nudity", "nude", "family", "safe%20for"):
        check(bad not in url, f"в запрос художнику попало «{bad}»: {url}")


asyncio.run(prompt_sent())


# Разбор ответа проверки: SAFE / UNSAFE / пусто (раздумье съело токены) / блок фильтра
async def verdicts():
    import ai.gemini as g

    answers = {"text": ""}

    class Models:
        async def generate_content(self, **kw):
            return types.SimpleNamespace(text=answers["text"], prompt_feedback=answers.get("fb"))

    real = g.client
    images.image_is_unsafe = REAL_CHECK
    g.client = types.SimpleNamespace(aio=types.SimpleNamespace(models=Models()))
    answers["text"] = "SAFE"
    check(await images.image_is_unsafe(b"\xff\xd8") is False, "SAFE → можно")
    answers["text"] = "UNSAFE"
    check(await images.image_is_unsafe(b"\xff\xd8") is True, "UNSAFE → нельзя")
    answers["text"] = ""
    check(await images.image_is_unsafe(b"\xff\xd8") is None, "пустой ответ → не проверено")
    answers["fb"] = types.SimpleNamespace(block_reason="PROHIBITED_CONTENT")
    check(await images.image_is_unsafe(b"\xff\xd8") is True, "блок фильтра → нельзя")
    g.client = real


asyncio.run(verdicts())

if errors:
    print("❌ " + "\n❌ ".join(errors))
    sys.exit(1)
print("✅ Рисунки Мары: просьбы, лимиты и запасной художник работают.")
