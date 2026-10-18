"""
/срок: сколько человек в группе и когда вступил.

    python test_member_since.py                      — без базы проверяется только текст
    TEST_DATABASE_URL=postgresql://… python test_member_since.py
"""

import asyncio
import os
import pathlib
import sys
from datetime import date, datetime

sys.path.insert(0, str(pathlib.Path(__file__).parent))
DB_URL = os.getenv("TEST_DATABASE_URL", "")
os.environ.setdefault("DATABASE_URL", DB_URL or "postgresql+asyncpg://x:y@127.0.0.1:1/z")

from features.member_since import format_since, span_text  # noqa: E402

errors, checks = [], 0


def check(ok, what):
    global checks
    checks += 1
    if not ok:
        errors.append(what)


check([span_text(d) for d in (1, 3, 5, 21, 365, 366, 800)] ==
      ["1 день", "3 дня", "5 дней", "21 день", "1 год", "1 год и 1 день", "2 года и 70 дней"], "склонения срока")

text = format_since("Вася", datetime(2026, 10, 12, 9), date(2026, 10, 18), True, False)
check("с <b>12.10.2026</b> — уже <b>6 дней</b>" in text, f"точная дата: {text}")
check("как минимум" in format_since("Вася", datetime(2026, 10, 12), date(2026, 10, 18), False, False), "до Мары — «как минимум»")
check("новичок" in format_since("Вася", datetime(2026, 10, 18), date(2026, 10, 18), True, False), "зашёл сегодня")
check("уже не в группе" in format_since("Вася", datetime(2026, 10, 12), date(2026, 10, 18), True, True), "вышел")
check("&lt;b&gt;" in format_since("<b>", datetime(2026, 10, 12), date(2026, 10, 18), True, False), "имя экранировано")


async def database():
    import random

    from database.database import init_db
    from database.repository import ensure_member, mark_joined, mark_member_left, member_since

    await init_db()
    chat, old, new = -100666000000 - random.randint(0, 10**6), 11, 12

    check(await member_since(chat, old) is None, "незнакомец — None")
    await ensure_member(chat, old, "Старожил")
    info = await member_since(chat, old)
    check(info and not info["exact"], f"был до Мары — неточная дата: {info}")

    # Вход есть в журнале Мары — дата точная, даже без joined_exact
    from datetime import datetime as _dt

    from database.database import session_scope
    from database.models import AuditEvent

    logged_user = 13
    await ensure_member(chat, logged_user, "Из журнала")
    async with session_scope() as session:
        session.add(AuditEvent(chat_id=chat, category="member", action="join", actor_kind="system",
                               target_id=logged_user, created_at=_dt(2026, 9, 1, 12)))
        await session.commit()
    info = await member_since(chat, logged_user)
    check(info and info["exact"] and info["joined_at"] == _dt(2026, 9, 1, 12), f"дата из журнала: {info}")

    await ensure_member(chat, new, "Новичок")
    await mark_member_left(chat, new, True)
    await mark_joined(chat, new)
    info = await member_since(chat, new)
    check(info and info["exact"] and info["left_at"] is None, f"зашёл при Маре — точная дата, не «вышел»: {info}")


if DB_URL:
    asyncio.run(database())
else:
    print("   (без TEST_DATABASE_URL база не проверялась)")

if errors:
    print(f"❌ {len(errors)} из {checks} проверок не прошли:")
    print("\n".join("  " + e for e in errors))
    sys.exit(1)

print(f"✅ Все {checks} проверок /срок прошли.")
