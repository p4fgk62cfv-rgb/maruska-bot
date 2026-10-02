"""Вход в приложение Арены через Мару.  python test_arena_login.py"""

import asyncio
import os
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", os.getenv("TEST_DATABASE_URL", "") or "postgresql://unused@localhost/unused")

import features.arena_login as al  # noqa: E402

failures, checks = [], 0


def expect(label, got, want):
    global checks
    checks += 1
    if got != want:
        failures.append(f"  {label}: получили {got!r}, ждали {want!r}")


class Chat:
    type = "private"


class Msg:
    def __init__(self):
        self.chat = Chat()
        self.sent = []
        self.edited = []

    async def answer(self, text, reply_markup=None):
        self.sent.append((text, reply_markup))

    async def edit_text(self, text):
        self.edited.append(text)


class Callback:
    def __init__(self, data, uid=42):
        self.data = data
        self.message = Msg()
        self.from_user = types.SimpleNamespace(id=uid, first_name="Вася", last_name=None, username="vasya", language_code="ru", is_premium=False)
        self.answers = []

    async def answer(self, text=None, show_alert=False):
        self.answers.append(text)


async def main():
    rid = "AbCdEfGhJk2345678mnp"
    expect("код из ссылки", al._request_id(f"alogin_{rid}"), rid)
    expect("чужой start", al._request_id("game_ABCD1234"), None)
    expect("мусор", al._request_id("alogin_../../x"), None)
    expect("пусто", al._request_id(None), None)

    calls = []

    async def fake(method, path, body=None):
        calls.append((method, path, body))
        if path.endswith("/confirm"):
            return (200, {"name": "Вася"}) if path.startswith(f"app-login/{rid}") else (404, {"error": "NOT_FOUND"})
        return (200, {"device": "Android · Chrome", "confirmed": False}) if rid in path else (404, {})

    al._arena = fake

    m = Msg()
    await al.ask_login(m, types.SimpleNamespace(args=f"alogin_{rid}"))
    text, kb = m.sent[0]
    expect("показывает устройство", "Android · Chrome" in text, True)
    expect("кнопка «Войти»", kb.inline_keyboard[0][0].callback_data, f"alogin:{rid}")

    m2 = Msg()
    await al.ask_login(m2, types.SimpleNamespace(args="alogin_ZZZZZZZZZZZZ"))
    expect("устаревшая ссылка", m2.sent[0][0], al.EXPIRED)

    cb = Callback(f"alogin:{rid}")
    await al.confirm_login(cb)
    expect("подтверждение уходит с данными человека", calls[-1][2]["user"]["id"], 42)
    expect("сообщение после входа", cb.message.edited[0].startswith("✅"), True)

    cb2 = Callback("alogin:ZZZZZZZZZZZZ")
    await al.confirm_login(cb2)
    expect("ошибка — понятный текст", cb2.message.edited[0], al.EXPIRED)

    group = Callback(f"alogin:{rid}")
    group.message.chat.type = "group"
    n = len(calls)
    await al.confirm_login(group)
    expect("в группе ничего не подтверждаем", len(calls), n)


asyncio.run(main())
if failures:
    print(f"ОШИБКИ ({len(failures)} из {checks}):")
    print("\n".join(failures))
    sys.exit(1)
print(f"OK: {checks} проверок")
