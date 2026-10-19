"""
/игры — меню всех игр кнопками: крокодил, крестики-нолики, шашки, морской бой,
КНБ, орёл или решка, Арена и Рыбалка; /гайд вместо /help.
Запуск:  python test_games_menu.py
"""

import asyncio
import os
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).parent))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:y@127.0.0.1:1/z")

from aiogram.filters import Command  # noqa: E402

import games.table as table  # noqa: E402
from features import basic  # noqa: E402
from fishing import service as fishing_service  # noqa: E402
from webapp import server  # noqa: E402

errors = []

os.environ["ARENA_APP_NAME"] = "play"
os.environ["ARENA_URL"] = "https://arena.example"
server.public_url = lambda: "https://bot.example"
fishing_service.settings = lambda: {"enabled": True}


async def me():
    return types.SimpleNamespace(username="BotMaruska_bot")


async def main():
    shown = []

    async def answer(text, reply_markup=None):
        shown.append(reply_markup)

    m = types.SimpleNamespace(
        bot=types.SimpleNamespace(me=me), answer=answer,
        chat=types.SimpleNamespace(id=-100, type="supergroup"),
    )
    await table.menu(m)
    texts = [b.text for row in shown[0].inline_keyboard for b in row]
    for want in ("Крокодил", "Крестики", "Шашки", "Морской бой", "Камень", "Орёл", "Арена", "Рыбалка"):
        if not any(want in t for t in texts):
            errors.append(f"в /игры нет кнопки «{want}»: {texts}")

    # Кнопка «Крокодил» запускает раунд
    started = []
    import games.crocodile as croc

    async def fake_start(message):
        started.append(message)

    croc.start_round = fake_start

    async def cb_answer(*a, **k):
        pass

    cb = types.SimpleNamespace(data="tm:croc", answer=cb_answer, message=m, from_user=types.SimpleNamespace(id=1))
    await table.menu_pick(cb)
    if started != [m]:
        errors.append("кнопка «Крокодил» не запустила раунд")


asyncio.run(main())

# /гайд — команда помощи (и /help по-старому)
handler = basic.help_handler
names = set()
for h in basic.router.message.handlers:
    if h.callback is handler:
        for f in h.filters:
            if isinstance(f.callback, Command):
                names |= {c if isinstance(c, str) else c.pattern for c in f.callback.commands}
if not {"гайд", "help"} <= names:
    errors.append(f"/гайд не подключён: {names}")
if "/гайд" not in basic.ABILITIES_TEXT or "/help" in basic.ABILITIES_TEXT:
    errors.append("«что ты умеешь» ссылается на /гайд")

if errors:
    print("❌ " + "\n❌ ".join(errors))
    sys.exit(1)
print("✅ /игры и /гайд: все проверки прошли.")
