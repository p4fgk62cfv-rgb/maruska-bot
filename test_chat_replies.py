"""
Ответ Маре одними смайлами, стикером или гифкой — Мара молчит.
Запуск:  python test_chat_replies.py
"""

import os
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).parent))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:y@127.0.0.1:1/z")

import botcontext  # noqa: E402
from features import chat  # noqa: E402

errors = []

botcontext.BOT_ID = 777
chat.is_enabled = lambda chat_id, key: True
chat.is_blocked = lambda chat_id, user_id: False
chat.get_value = lambda chat_id, key: "normal"
chat.within_limits = lambda chat_id, user_id: True

mara = types.SimpleNamespace(from_user=types.SimpleNamespace(id=777, is_bot=True))
other = types.SimpleNamespace(from_user=types.SimpleNamespace(id=5, is_bot=False))


def msg(text, reply=None):
    return types.SimpleNamespace(
        text=text, caption=None, reply_to_message=reply,
        chat=types.SimpleNamespace(id=-100, type="supergroup"),
        from_user=types.SimpleNamespace(id=1, is_bot=False),
    )


cases = [
    ("😂", mara, False),
    ("❤️❤️🔥", mara, False),
    (")))", mara, False),
    (None, mara, False),          # стикер или гифка без подписи
    ("ахах 😂", mara, True),
    ("ок", mara, True),
    ("Мара, привет 😂", None, True),
    ("😂", other, False),
]
for text, reply, want in cases:
    got = chat.should_answer(msg(text, reply))
    if got != want:
        errors.append(f"{text!r} в ответ {'Маре' if reply is mara else 'другому'}: {got}, ждали {want}")

if errors:
    print("❌ " + "\n❌ ".join(errors))
    sys.exit(1)
print("✅ Ответы смайлами Маре: все проверки прошли.")
