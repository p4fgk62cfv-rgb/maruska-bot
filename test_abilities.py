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

if errors:
    print("❌ " + "\n❌ ".join(errors))
    sys.exit(1)
print("✅ «Что ты умеешь»: все проверки прошли.")
