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


check(mt.parse_start("турнир 5000") == ("start", 5000), "сумма")
check(mt.parse_start("Турнир 5 000") == ("start", 5000), "сумма с пробелом")
check(mt.parse_start("турнир") == ("start", None), "без суммы")
check(mt.parse_start("игра 5000") is None, "не турнир")
check(mt.parse_start(None) is None, "пусто")
text = mt.signup_text(5000, [{"id": 1, "name": "<Стас>"}])
check("5 000 кредитов в игре «Дурак Онлайн»" in text and "&lt;Стас&gt;" in text and "(1/6)" in text and "6. —" in text, f"текст записи: {text}")
check("запись закрыта" in mt.signup_text(5000, [{"id": i, "name": str(i)} for i in range(6)], closed=True), "закрыто")


class FakeBot:
    def __init__(self):
        self.edits = []

    async def edit_message_text(self, text, chat_id, message_id):
        self.edits.append(text)


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

    async def fake_arena(method, path, body=None, query=None):
        calls.append((method, path, body, query))
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
    check(await get_mini_signup(chat) is None, "запись закрыта в базе")

    await press("mt:join", 17, "Опоздавший")
    check(alerts[-1] == "Запись уже закрыта.", "после закрытия кнопки не работают")

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
