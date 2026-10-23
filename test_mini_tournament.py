"""
Мини-турнир: запись у Мары (/старт турнир 5000), кнопки, список, передача Арене.

    TEST_DATABASE_URL=postgresql://… python test_mini_tournament.py
"""

import asyncio
import os
import pathlib
import random
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).parent))
DB_URL = os.getenv("TEST_DATABASE_URL", "")
os.environ.setdefault("DATABASE_URL", DB_URL or "postgresql+asyncpg://x:y@127.0.0.1:1/z")

import features.mini_tournament as mt  # noqa: E402
import settings.handler as sh  # noqa: E402

errors = []


def check(ok, what):
    if not ok:
        errors.append(what)


check(mt.parse_start("турнир 5000") == ("start", 5000, 1), "сумма")
check(mt.parse_start("Турнир 5 000") == ("start", 5000, 1), "сумма с пробелом")
check(mt.parse_start("турнир") == ("start", None, 1), "без суммы")
check(mt.parse_start("турнир2 5000") == ("start", 5000, 2), "два стола")
check(mt.parse_start("Турнир2") == ("start", None, 2), "два стола без суммы")
check(mt.parse_start("турнир3 5000") is None, "трёх столов нет")
check(mt.parse_start("игра 5000") is None, "не турнир")
check(mt.parse_start(None) is None, "пусто")
text = mt.signup_text(5000, [{"id": 1, "name": "<Стас>"}])
check("5 000 кредитов в игре «Дурак Онлайн»" in text and "&lt;Стас&gt;" in text and "(1/6)" in text and "6. —" in text, f"текст записи: {text}")
check("запись закрыта" in mt.signup_text(5000, [{"id": i, "name": str(i)} for i in range(6)], closed=True), "закрыто")

# Настройки из админки: границы, выбор, текст с подстановками и **жирным**
cleaned = mt.clean_settings({"seats": 9, "ready_seconds": 5, "variant": "podkidnoy", "speed": "чепуха", "text": "  ", "photo": {"x": 1}})
check(cleaned["seats"] == 6 and cleaned["ready_seconds"] == 15 and cleaned["variant"] == "podkidnoy"
      and cleaned["speed"] == "fast" and cleaned["text"] == mt.DEFAULT_TEXT and cleaned["photo"] is None, f"очистка: {cleaned}")
custom = mt.clean_settings({"seats": 4, "ready_seconds": 90, "text": "**Турнир!** <script> Приз {prize}, мест {seats}, ждём {seconds} с. {rules}"})
intro = mt.render_intro(custom, 12000)
check(intro.startswith("<b>Турнир!</b> &lt;script&gt;") and "Приз 12 000, мест 4, ждём 90 с." in intro
      and "Переводной · подкидывают все · быстрая игра · без ничьей" in intro, f"текст: {intro}")
four = mt.signup_text(100, [{"id": 1, "name": "А"}], settings=custom)
check("(1/4)" in four and "4. —" in four and "5. —" not in four, "мест — из настроек")
import html as _html  # noqa: E402
import re as _re  # noqa: E402
longest = mt.signup_text(10**9, [{"id": 10**12, "name": "Я" * mt.MAX_NAME}] * 6, closed=True,
                         settings=mt.clean_settings({"text": "x{rules}" * 400}))
visible = _html.unescape(_re.sub(r"<[^>]+>", "", longest))
check(len(visible) <= 1024, f"подпись к картинке влезает в 1024 видимых символа: {len(visible)}")
# Два стола: 12 мест, длинные имена укорачиваются, подпись всё равно влезает
two = mt.signup_text(10**9, [{"id": 10**12, "name": "Я" * mt.MAX_NAME}] * 12, closed=True,
                     settings=mt.clean_settings({"text": "x{rules}" * 400, "tables": 2}))
visible = _html.unescape(_re.sub(r"<[^>]+>", "", two))
check(len(visible) <= 1024, f"два стола: подпись влезает в 1024 видимых символа: {len(visible)}")
check("(12/12)" in two and "Два стола по 6" in two and "ссылки на оба стола" in two, f"два стола: текст записи: {two}")
# Старый текст по умолчанию, сохранённый в настройках, не врёт про «один стол»
old = mt.render_intro(mt.clean_settings({"text": mt.OLD_DEFAULT_TEXT, "tables": 2}), 100)
check("один стол" not in old and "финал 1 на 1" in old, f"старый текст на два стола: {old}")
check("один стол" in mt.render_intro(mt.clean_settings({"text": mt.OLD_DEFAULT_TEXT}), 100), "старый текст на один стол")


class FakeBot:
    def __init__(self):
        self.edits = []

    async def edit_message_text(self, text, chat_id, message_id):
        self.edits.append(text)

    async def get_chat(self, chat_id):
        return types.SimpleNamespace(title=f"Группа {chat_id}")


def message(chat_id, uid, said, bot, admin=True):
    async def reply(t, **_):
        said.append(t)

    async def answer(t, reply_markup=None, **_):
        said.append(t)
        return types.SimpleNamespace(message_id=500 + len(said))

    return types.SimpleNamespace(
        chat=types.SimpleNamespace(id=chat_id, type="supergroup", title="Группа"),
        from_user=types.SimpleNamespace(id=uid, is_bot=False, first_name="Админ", username=None),
        sender_chat=None, bot=bot, reply=reply, answer=answer,
    )


def button(chat_id, message_id, data, uid, name, edits, alerts, bot):
    async def edit_text(t, reply_markup=None):
        edits.append((t, reply_markup))

    async def ans(t="", show_alert=False):
        alerts.append(t)

    msg = types.SimpleNamespace(chat=types.SimpleNamespace(id=chat_id), message_id=message_id, edit_text=edit_text, bot=bot)
    msg.answer = None
    return types.SimpleNamespace(message=msg, data=data, answer=ans,
                                 from_user=types.SimpleNamespace(id=uid, is_bot=False, first_name=name, username=f"u{uid}"))


async def scenario():
    from database.database import init_db
    from database.repository import get_mini_signup

    await init_db()
    chat = -100880000000 - random.randint(0, 10**6)
    calls = []
    playing_now = {}

    async def fake_arena(method, path, body=None, query=None):
        calls.append((method, path, body, query))
        if path == "mini-tournaments/playing":
            return 200, {"tournament": playing_now.get(query["telegramId"])}
        if path == "mini-tournaments/active":
            return 200, {"tournament": None}
        if path == "mini-tournaments":
            return 200, {"id": "t1"}
        if path == "mini-tournaments/cancel":
            return 200, {"cancelled": False}
        return 404, {}

    mt._arena = fake_arena

    async def admin(event, bot):
        return event.from_user.id == 1

    sh.is_admin = admin
    bot = FakeBot()

    # Не админ не запускает; без суммы — подсказка
    said = []
    await mt.open_signup(message(chat, 2, said, bot), 5000)
    check(said and "только админы" in said[0], f"не админ: {said}")
    said = []
    await mt.open_signup(message(chat, 1, said, bot), None)
    check(said and "Укажи призовой фонд" in said[0], f"без суммы: {said}")

    said = []
    await mt.open_signup(message(chat, 1, said, bot), 5000)
    signup = await get_mini_signup(chat)
    check(signup is not None and signup.prize == 5000 and signup.organizer_id == 1, "запись сохранена")
    check(said and "Участники (0/6)" in said[0], f"сообщение записи: {said}")
    said2 = []
    await mt.open_signup(message(chat, 1, said2, bot), 100)
    check(said2 and "уже идёт" in said2[0], "вторая запись не открывается")

    edits, alerts = [], []
    mid = signup.message_id

    async def press(data, uid, name):
        await mt.signup_button(button(chat, mid, data, uid, name, edits, alerts, bot))

    # Записываются, кто-то передумал, кто-то жмёт дважды
    await press("mt:join", 10, "Аня")
    check("Аня" in edits[-1][0] and "(1/6)" in edits[-1][0] and edits[-1][1] is not None, "Аня в списке")
    await press("mt:join", 10, "Аня")
    check(alerts[-1] == "Ты уже записан ✅", "повторная запись")
    await press("mt:leave", 10, "Аня")
    check("(0/6)" in edits[-1][0], "Аня вышла")
    await press("mt:leave", 10, "Аня")
    check("нет в списке" in alerts[-1], "выйти, не записавшись")
    for uid, name in [(11, "Боря"), (12, "Вика"), (13, "Гоша"), (14, "Даня"), (15, "Ева")]:
        await press("mt:join", uid, name)
    check(not any(c[1] == "mini-tournaments" for c in calls), "пятерых мало — Арену не зовём")
    await press("mt:join", 16, "Женя")

    last_text, last_kb = edits[-1]
    check("запись закрыта" in last_text and last_kb is None, "шестой — кнопки пропали")
    start = [c for c in calls if c[1] == "mini-tournaments"]
    check(len(start) == 1, f"Арене передан состав один раз: {start}")
    body = start[0][2]
    check(body["chatId"] == str(chat) and body["prize"] == 5000 and body["organizer"]["telegramId"] == "1", f"тело: {body}")
    check([p["name"] for p in body["players"]] == ["Боря", "Вика", "Гоша", "Даня", "Ева", "Женя"], "состав по порядку записи")
    check(body["rules"] == {"variant": "perevodnoy", "throwIn": "all", "speed": "fast", "readySeconds": 60}, f"правила: {body['rules']}")
    check(await get_mini_signup(chat) is None, "запись закрыта в базе")
    check(body["tables"] == 1, f"один стол: {body.get('tables')}")

    await press("mt:join", 17, "Опоздавший")
    check(alerts[-1] == "Запись уже закрыта.", "после закрытия кнопки не работают")

    # Настройки из админки: 3 места, подкидной, 2 минуты, своя картинка
    await mt.save_settings({"seats": 3, "variant": "podkidnoy", "ready_seconds": 120, "photo": {"file_id": "PHOTO1", "name": "кубок"}})
    photos, captions = [], []
    m = message(chat, 1, [], bot)

    async def answer_photo(file_id, caption=None, reply_markup=None):
        photos.append((file_id, caption))
        return types.SimpleNamespace(message_id=900)

    m.answer_photo = answer_photo
    await mt.open_signup(m, 1000)
    check(photos and photos[0][0] == "PHOTO1" and "(0/3)" in photos[0][1], f"объявление с картинкой: {photos}")
    mid = 900
    calls.clear()

    def photo_button(uid, name):
        cb = button(chat, mid, "mt:join", uid, name, edits, alerts, bot)

        async def edit_caption(caption=None, reply_markup=None):
            captions.append((caption, reply_markup))

        cb.message.edit_caption = edit_caption
        return cb

    for uid, name in [(31, "Ира"), (32, "Кеша"), (33, "Лена")]:
        await mt.signup_button(photo_button(uid, name))
    check(captions and "(2/3)" in captions[1][0] and captions[-1][1] is None and "запись закрыта" in captions[-1][0], "картинка: подпись правится, на 3-м закрыто")
    start3 = [c for c in calls if c[1] == "mini-tournaments"]
    check(start3 and len(start3[0][2]["players"]) == 3 and start3[0][2]["rules"]["variant"] == "podkidnoy"
          and start3[0][2]["rules"]["readySeconds"] == 120, f"3 места и правила: {start3}")
    await mt.save_settings({"seats": 6, "variant": "perevodnoy", "ready_seconds": 60, "photo": None})

    # Два стола: /старт турнир2 — 12 мест, Арене уходят все 12 и tables=2
    said = []
    await mt.open_signup(message(chat, 1, said, bot), 8000, 2)
    check(said and "Участники (0/12)" in said[0] and "Два стола" not in said[0] and "два стола по 6" in said[0], f"запись на два стола: {said}")
    signup = await get_mini_signup(chat)
    mid = signup.message_id
    calls.clear()
    for uid in range(40, 52):
        await press("mt:join", uid, f"Игрок{uid}")
        if uid == 50:
            check(not any(c[1] == "mini-tournaments" for c in calls), "11 из 12 — Арену не зовём")
    two_start = [c for c in calls if c[1] == "mini-tournaments"]
    check(len(two_start) == 1 and two_start[0][2]["tables"] == 2 and len(two_start[0][2]["players"]) == 12,
          f"два стола: Арене переданы 12 человек и tables=2: {two_start}")
    check("(12/12)" in edits[-1][0] and "запись закрыта" in edits[-1][0], "два стола: запись закрыта на 12-м")

    # Отмена записи
    said = []
    await mt.open_signup(message(chat, 1, said, bot), 300)
    said = []
    await mt.stop_tournament(message(chat, 1, said, bot))
    check(said and "отменена" in said[-1] and bot.edits and "отменён" in bot.edits[-1], f"отмена записи: {said}")
    check(await get_mini_signup(chat) is None, "запись удалена")
    said = []
    await mt.stop_tournament(message(chat, 1, said, bot))
    check(said and "нет турнира" in said[-1], "отменять нечего")

    # Один человек — один турнир: записан в другой группе или ещё играет там — сюда нельзя
    from database.repository import delete_mini_signup

    chat_a, chat_b = chat - 1, chat - 2
    mids = {}
    for c in (chat_a, chat_b):
        await mt.open_signup(message(c, 1, [], bot), 500)
        mids[c] = (await get_mini_signup(c)).message_id

    async def press_in(c, data, uid, name):
        await mt.signup_button(button(c, mids[c], data, uid, name, edits, alerts, bot))

    await press_in(chat_a, "mt:join", 70, "Двойной")
    check(alerts[-1].startswith("Ты в турнире"), f"в первой группе записался: {alerts[-1]}")
    await press_in(chat_b, "mt:join", 70, "Двойной")
    check("уже записан на турнир в группе «Группа " + str(chat_a) + "»" in alerts[-1], f"во второй — нельзя: {alerts[-1]}")
    check(not (await get_mini_signup(chat_b)).players, "во второй группе его нет в списке")
    await press_in(chat_a, "mt:leave", 70, "Двойной")
    await press_in(chat_b, "mt:join", 70, "Двойной")
    check(alerts[-1].startswith("Ты в турнире"), f"вышел из первой — записался во вторую: {alerts[-1]}")
    playing_now["71"] = {"chatId": str(chat_a)}
    await press_in(chat_b, "mt:join", 71, "Играет")
    check("сейчас играешь турнир в группе" in alerts[-1], f"ещё играет турнир в другой группе: {alerts[-1]}")
    playing_now.clear()
    await press_in(chat_b, "mt:join", 71, "Играет")
    check(alerts[-1].startswith("Ты в турнире"), f"выбыл там — записался: {alerts[-1]}")
    for c in (chat_a, chat_b):
        await delete_mini_signup(c)

    # Арена не ответила — честно говорим и предлагаем запустить снова
    async def broken(method, path, body=None, query=None):
        if path == "mini-tournaments":
            return 502, {"error": "ARENA_UNREACHABLE"}
        return 200, {"tournament": None}

    mt._arena = broken
    said = []
    await mt.open_signup(message(chat, 1, said, bot), 700)
    signup = await get_mini_signup(chat)
    mid = signup.message_id
    out = []

    async def answer_out(t, **_):
        out.append(t)

    for uid in range(20, 26):
        cb = button(chat, mid, "mt:join", uid, f"И{uid}", edits, alerts, bot)
        cb.message.answer = answer_out
        await mt.signup_button(cb)
    check(out and "Не получилось открыть стол" in out[-1] and "/старт турнир 700" in out[-1], f"Арена молчит: {out}")


if DB_URL:
    asyncio.run(scenario())
else:
    print("ℹ️  TEST_DATABASE_URL не задан — сценарий с базой пропущен")

if errors:
    print("❌ " + "\n❌ ".join(errors))
    sys.exit(1)
print("✅ Мини-турнир (запись у Мары): все проверки прошли.")
