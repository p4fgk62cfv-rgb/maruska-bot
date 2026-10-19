"""
«Мара, что ты умеешь» — Мара сама рассказывает о возможностях.
Запуск:  python test_abilities.py
"""

import os
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).parent))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:y@127.0.0.1:1/z")

import botcontext  # noqa: E402
from features import basic  # noqa: E402

errors = []
botcontext.BOT_ID = 777
botcontext.BOT_USERNAME = "BotMaruska_bot"

mara = types.SimpleNamespace(from_user=types.SimpleNamespace(id=777, is_bot=True))


def msg(text, reply=None, private=False, bot=False):
    return types.SimpleNamespace(
        text=text, caption=None, reply_to_message=reply,
        chat=types.SimpleNamespace(id=-100, type="private" if private else "supergroup"),
        from_user=types.SimpleNamespace(id=1, is_bot=bot),
    )


cases = [
    ("Мара что ты умеешь", None, True),
    ("Маруся, что ты умеешь?", None, True),
    ("мара, что ты можешь", None, True),
    ("Маруся, какие у тебя функции", None, True),
    ("Мара покажи свои команды", None, True),
    ("Мара, помощь", None, True),
    ("@BotMaruska_bot что ты умеешь", None, True),
    ("что ты умеешь", mara, True),          # ответом на сообщение Мары
    ("что ты умеешь", None, False),         # к Маре не обращались
    ("Вася, что ты умеешь", None, False),
    ("/help", None, False),
    ("Мара, как дела?", None, False),
    ("Мара, что такое кордиал", None, False),
]
for text, reply, want in cases:
    got = basic.asks_abilities(msg(text, reply))
    if got != want:
        errors.append(f"{text!r}: {got}, ждали {want}")
if not basic.asks_abilities(msg("что ты умеешь", private=True)):
    errors.append("в личке спрашивают без имени")
if basic.asks_abilities(msg("Мара что ты умеешь", bot=True)):
    errors.append("бот не спрашивает")

if len(basic.ABILITIES_TEXT) > 4000:
    errors.append(f"текст длиннее лимита Telegram: {len(basic.ABILITIES_TEXT)}")
for word in ("/warn", "/mute", "/ban", "/settings", "/kick", "/lock"):
    if word in basic.ABILITIES_TEXT:
        errors.append(f"админская команда в рассказе для людей: {word}")

# Кнопки «Арена» и «Рыбалка»: в личке — web_app, в группе — ссылки t.me
import asyncio  # noqa: E402

from fishing import service as fishing_service  # noqa: E402
from games import arena as arena_game  # noqa: E402
from settings import store  # noqa: E402
from webapp import server  # noqa: E402

os.environ["ARENA_URL"] = "https://arena.example"
os.environ["ARENA_APP_NAME"] = "play"
server.public_url = lambda: "https://bot.example"
fishing_service.settings = lambda: {"enabled": True}
store.is_enabled = lambda chat_id, key: True


class Bot:
    async def me(self):
        return types.SimpleNamespace(username="BotMaruska_bot")


def with_bot(m):
    m.bot = Bot()
    return m


async def keyboard(m):
    kb = await basic._abilities_keyboard(with_bot(m))
    return [b for row in kb.inline_keyboard for b in row] if kb else []


async def check_buttons():
    group = await keyboard(msg("x"))
    if [b.text for b in group] != ["🃏 Арена — дурак онлайн", "🎣 Рыбалка"]:
        errors.append(f"кнопки в группе: {[b.text for b in group]}")
    elif group[0].url != "https://t.me/BotMaruska_bot/play" or not group[1].url.startswith("https://t.me/BotMaruska_bot/fishing?startapp=g"):
        errors.append(f"ссылки в группе: {[b.url for b in group]}")
    private = await keyboard(msg("x", private=True))
    if len(private) != 2 or not all(b.web_app for b in private):
        errors.append("в личке кнопки открывают приложение внутри Telegram")
    os.environ["ARENA_URL"] = ""
    only_fishing = await keyboard(msg("x", private=True))
    if [b.text for b in only_fishing] != ["🎣 Рыбалка"]:
        errors.append("без адреса Арены кнопки Арены нет")
    store.is_enabled = lambda chat_id, key: key != "fishing"
    none_left = await keyboard(msg("x"))
    if any("Рыбалка" in b.text for b in none_left):
        errors.append("рыбалка выключена в группе — кнопки нет")


asyncio.run(check_buttons())
if "🃏 <b>Арена</b>" not in basic.ABILITIES_TEXT:
    errors.append("в рассказе нет Арены")

if errors:
    print("❌ " + "\n❌ ".join(errors))
    sys.exit(1)
print("✅ «Что ты умеешь»: все проверки прошли.")
