"""
Топ болтунов: что считается сообщением.
Запуск:  python test_chatters_count.py
"""

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:y@127.0.0.1:1/z")

from aiogram.types import Chat, Message, User  # noqa: E402

from settings.middleware import is_service  # noqa: E402

errors = []

chat = Chat(id=-100777, type="supergroup")
user = User(id=1, is_bot=False, first_name="Вася")


def msg(**fields):
    return Message(message_id=1, date=0, chat=chat, from_user=user, **fields)


def check(ok, what):
    if not ok:
        errors.append(what)


check(not is_service(msg(text="привет")), "обычный текст — сообщение")
check(not is_service(msg(sticker={"file_id": "s", "file_unique_id": "u", "type": "regular", "width": 1, "height": 1, "is_animated": False, "is_video": False})), "стикер — сообщение")
check(is_service(msg(new_chat_members=[user])), "вход в группу — не сообщение")
check(is_service(msg(left_chat_member=user)), "выход — не сообщение")
check(is_service(msg(new_chat_title="БЛЕФ🃏")), "смена названия — не сообщение")
check(is_service(msg(pinned_message=msg(text="важно"))), "закреп — не сообщение")

if errors:
    print(f"❌ {len(errors)} проверок не прошли:")
    print("\n".join("  " + e for e in errors))
    sys.exit(1)

print("✅ Все 6 проверок подсчёта сообщений прошли.")
