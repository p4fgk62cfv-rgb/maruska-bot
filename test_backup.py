"""
Ночной бэкап базы: выгрузка pg_dump, отправка файлом, части, ошибки.

    TEST_DATABASE_URL=postgresql://… python test_backup.py
"""

import asyncio
import os
import pathlib
import shutil
import sys
import types
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).parent))
DB_URL = os.getenv("TEST_DATABASE_URL", "")
os.environ.setdefault("DATABASE_URL", DB_URL or "postgresql+asyncpg://x:y@127.0.0.1:1/z")

from features import backup  # noqa: E402

errors = []


def check(ok, what):
    if not ok:
        errors.append(what)


# Адрес для pg_dump и пароль в сообщениях
REAL_URL = os.environ["DATABASE_URL"]
os.environ["DATABASE_URL"] = "postgresql+asyncpg://user:s3cret@db.internal:5432/railway"
check(backup.database_url() == "postgresql://user:s3cret@db.internal:5432/railway", "адрес без +asyncpg")
os.environ["DATABASE_URL"] = REAL_URL
hidden = backup.hide_secrets("connection to postgresql://user:s3cret@db.internal:5432/railway failed")
check("s3cret" not in hidden and "user:***@db.internal" in hidden, f"пароль скрыт: {hidden}")

# Части по 45 МБ, размеры, расписание
check([len(p) for p in backup.parts_of(b"x" * 10, 4)] == [4, 4, 2], "деление на части")
check(backup.human_size(2 * 1024 * 1024 + 300_000) == "2,3 МБ" and backup.human_size(500) == "1 КБ", "размер")
night = datetime(2026, 10, 21, backup.BACKUP_HOUR, 5, tzinfo=backup.MSK)
check(backup.due(night, {}) and not backup.due(night, {"day": "2026-10-21"}), "раз в сутки")
check(not backup.due(night.replace(hour=max(backup.BACKUP_HOUR - 1, 0)), {}) or backup.BACKUP_HOUR == 0, "до часа — рано")
check(backup.recipient_setting() == "uastas", "по умолчанию — @uastas")


class FakeBot:
    def __init__(self):
        self.documents, self.messages = [], []

    async def send_document(self, chat_id, document, caption=None, **kwargs):
        # Как Telegram: в HTML-режиме «<адрес базы>» — ошибка разбора
        if kwargs.get("parse_mode", "HTML") is not None and "<адрес" in (caption or ""):
            raise RuntimeError("can't parse entities")
        self.documents.append((chat_id, document.filename, document.data, caption))

    async def send_message(self, chat_id, text, **kwargs):
        self.messages.append((chat_id, text))


async def scenario():
    from database.database import init_db

    await init_db()
    os.environ["BACKUP_TO"] = "424242"

    # Удачный бэкап: файл pg_dump (формат custom начинается с PGDMP) — в личку
    bot = FakeBot()
    state = await backup.run_backup(bot, reason="тест")
    check(len(bot.documents) == 1 and bot.documents[0][0] == 424242, f"файл отправлен: {[d[:2] for d in bot.documents]}")
    if bot.documents:
        _, name, data, caption = bot.documents[0]
        check(data[:5] == b"PGDMP" and name.startswith("maruska-") and name.endswith(".dump"), f"формат: {name} {data[:5]}")
        check("Бэкап базы Маруськи (тест)" in caption and "pg_restore" in caption, f"подпись: {caption}")
    check(state.get("ok_at") and not state.get("error") and state.get("size", 0) > 1000, f"состояние: {state}")
    check(not backup.due(datetime.now(backup.MSK), await backup.load_state()), "сегодня уже сделан")

    # Большая база — частями
    old = backup.PART_SIZE
    backup.PART_SIZE = 50_000
    bot = FakeBot()
    await backup.run_backup(bot, reason="тест")
    backup.PART_SIZE = old
    names = [d[1] for d in bot.documents]
    check(len(names) > 1 and names[0].endswith(".part1") and "Часть 1 из" in bot.documents[0][3], f"части: {names}")

    # Ошибка: сообщение с причиной, без пароля
    os.environ["DATABASE_URL"] = "postgresql://user:s3cret@127.0.0.1:1/nope"  # движок бота уже создан — ломаем только pg_dump
    bot = FakeBot()
    state = await backup.run_backup(bot, reason="тест")
    check(not bot.documents and bot.messages and "не получился" in bot.messages[0][1]
          and "s3cret" not in bot.messages[0][1], f"ошибка: {bot.messages}")
    check(state.get("error") and "s3cret" not in state["error"], f"ошибка в состоянии: {state}")
    os.environ["DATABASE_URL"] = REAL_URL
    await backup.save_state(day=None, error=None)


if DB_URL and shutil.which("pg_dump"):
    asyncio.run(scenario())
else:
    print("⚠️ Без TEST_DATABASE_URL или pg_dump — только проверки без базы")

if errors:
    print("❌ " + "\n❌ ".join(errors))
    sys.exit(1)
print("✅ Бэкап базы: все проверки прошли.")
