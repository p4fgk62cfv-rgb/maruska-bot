"""Кого наказывает /mute, /unmute, /ban, /warn.  python test_mod_targets.py (с TEST_DATABASE_URL — и по @username)"""

import asyncio
import os
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))
DB_URL = os.getenv("TEST_DATABASE_URL", "")
os.environ.setdefault("DATABASE_URL", DB_URL or "postgresql://unused@localhost/unused")

from features.moderation import _minutes, _target_of  # noqa: E402

failures, checks = [], 0


def expect(label, got, want):
    global checks
    checks += 1
    if got != want:
        failures.append(f"  {label}: получили {got!r}, ждали {want!r}")


def user(uid, bot=False):
    return types.SimpleNamespace(id=uid, is_bot=bot, first_name=f"U{uid}", username=None)


def msg(text, reply=None, external=None, entities=None):
    return types.SimpleNamespace(
        text=text, reply_to_message=types.SimpleNamespace(from_user=reply) if reply else None,
        external_reply=external, entities=entities or [], chat=types.SimpleNamespace(id=-100777),
    )


async def main():
    expect("ответ на сообщение", (await _target_of(msg("/unmute", reply=user(5)))).id, 5)
    expect("ответ боту не считается", await _target_of(msg("/unmute", reply=user(6, bot=True))), None)
    old = types.SimpleNamespace(origin=types.SimpleNamespace(sender_user=user(7)))
    expect("ответ на старое сообщение (до супергруппы)", (await _target_of(msg("/unmute", external=old))).id, 7)
    mention = types.SimpleNamespace(type="text_mention", user=user(8))
    expect("упоминание без @username", (await _target_of(msg("/mute Вася", entities=[mention]))).id, 8)
    expect("ничего не указано", await _target_of(msg("/unmute")), None)
    expect("короткое число — срок, не человек", await _target_of(msg("/mute 30")), None)

    expect("срок после @username", _minutes(msg("/mute @vasya 30")), 30)
    expect("срок без человека", _minutes(msg("/mute 2ч")), 120)

    if DB_URL:
        from database.database import engine, init_db, session_scope
        from database.models import User
        from sqlalchemy import delete

        await init_db()
        async with session_scope() as session:
            await session.execute(delete(User).where(User.telegram_id == 990011))
            session.add(User(telegram_id=990011, username="Olesya_FX1", first_name="Lesya"))
            await session.commit()
        found = await _target_of(msg("/unmute @olesya_fx1"))
        expect("@username без учёта регистра", (found.id, found.first_name), (990011, "Lesya"))
        expect("по ID", (await _target_of(msg("/ban 990011"))).id, 990011)
        expect("неизвестный @username", await _target_of(msg("/unmute @nobody_xyz")), None)
        async with session_scope() as session:
            await session.execute(delete(User).where(User.telegram_id == 990011))
            await session.commit()
        await engine.dispose()


asyncio.run(main())
if failures:
    print(f"❌ Ошибок: {len(failures)} из {checks}")
    print("\n".join(failures))
    sys.exit(1)
print(f"✅ Все {checks} проверок цели модерации прошли.")
