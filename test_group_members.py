"""
Участники группы, которые ещё ничего не писали: вошедшие по ссылке и админы.

    python test_group_members.py                      — без базы проверки пропускаются
    TEST_DATABASE_URL=postgresql://… python test_group_members.py
"""

import asyncio
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))

DB_URL = os.getenv("TEST_DATABASE_URL", "")
os.environ.setdefault("DATABASE_URL", DB_URL or "postgresql://unused@localhost/unused")

failures, checks = [], 0
CHAT = -100777000111


def expect(label, got, want):
    global checks
    checks += 1
    if got != want:
        failures.append(f"  {label}: получили {got!r}, ждали {want!r}")


async def with_database():
    from database.database import engine, init_db, session_scope
    from database.models import GroupMember
    from database.repository import ensure_member, list_known_chats, mark_chat_gone, move_chat, add_warning, count_warnings, mark_member_left, members_page, remember_chat, save_message
    from sqlalchemy import delete

    await init_db()
    async with session_scope() as session:
        await session.execute(delete(GroupMember).where(GroupMember.chat_id == CHAT))
        await session.commit()

    # Зашёл по ссылке и молчит — уже в списке, без выдуманного «был в сети».
    expect("новый молчун создан", await ensure_member(CHAT, 501, "Оля"), True)
    expect("повторный вход не дублирует", await ensure_member(CHAT, 501, "Оля"), False)
    page = await members_page([CHAT])
    expect("в списке", [u["telegram_id"] for u in page["users"]], [501])
    expect("имя", page["users"][0]["name"], "Оля")
    expect("не писал — нет «в сети»", page["users"][0]["last_seen"], None)

    # Два входа одновременно (событие и служебное сообщение) — одна запись.
    results = await asyncio.gather(ensure_member(CHAT, 502, "Петя"), ensure_member(CHAT, 502, "Петя"))
    expect("параллельный вход создаёт одну запись", sorted(results), [False, True])

    # Вышел и вернулся — снова в группе.
    await mark_member_left(CHAT, 501, True)
    expect("вышедший помечен", (await members_page([CHAT], flt="all"))["users"][0]["telegram_id"] in (501, 502), True)
    await ensure_member(CHAT, 501, "Оля")
    async with session_scope() as session:
        from sqlalchemy import select
        row = (await session.execute(select(GroupMember).where(GroupMember.chat_id == CHAT, GroupMember.telegram_id == 501))).scalar_one()
        expect("вернувшемуся снята отметка «вышел»", row.left_at, None)

    # Заговорил — появляется время активности.
    await save_message(CHAT, 502, "Петя", "привет", store_text=False)
    page = await members_page([CHAT])
    pete = next(u for u in page["users"] if u["telegram_id"] == 502)
    expect("после сообщения есть «был в сети»", pete["last_seen"] is not None, True)
    expect("сообщение посчитано", pete["messages"], 1)

    # Мару добавили в новую группу, где ещё никто не писал: группа сразу видна панели.
    NEW = CHAT - 1
    await remember_chat(NEW, "Пример теста")
    await remember_chat(NEW, "Пример теста")
    await ensure_member(NEW, 601, "Владелец")
    known = {c["chat_id"]: c for c in await list_known_chats()}
    expect("новая группа известна панели", NEW in known, True)
    expect("название группы", known.get(NEW, {}).get("title"), "Пример теста")

    # Мару удалили из группы — группа пропадает из панели; вернули — снова видна.
    await mark_chat_gone(NEW)
    await mark_chat_gone(NEW)
    expect("удалённая группа скрыта", NEW in {c["chat_id"] for c in await list_known_chats()}, False)
    await remember_chat(NEW, "Пример теста")
    expect("вернули — видна", NEW in {c["chat_id"] for c in await list_known_chats()}, True)

    # Группу сделали супергруппой: новый ID, всё переезжает
    from database.repository import get_group_settings, set_group_setting
    SUPER = -1009000000001
    await set_group_setting(chat_id=NEW, key="antimat", value=True)
    await add_warning(NEW, 601, "Мат")
    await move_chat(NEW, SUPER)
    known = {c["chat_id"] for c in await list_known_chats()}
    expect("старая группа скрыта", NEW in known, False)
    expect("новая видна", SUPER in known, True)
    expect("настройки переехали", (await get_group_settings(SUPER)).get("antimat"), True)
    expect("предупреждения переехали", await count_warnings(SUPER, 601), 1)
    await move_chat(NEW, SUPER)
    expect("повторный переезд безопасен", SUPER in {c["chat_id"] for c in await list_known_chats()}, True)

    from database.models import ChatWarning, GoneChat, GroupSettings
    async with session_scope() as session:
        await session.execute(delete(GroupMember).where(GroupMember.chat_id == SUPER))
        await session.execute(delete(GroupSettings).where(GroupSettings.chat_id == SUPER))
        await session.execute(delete(ChatWarning).where(ChatWarning.chat_id.in_([NEW, SUPER])))
        await session.execute(delete(GoneChat).where(GoneChat.chat_id.in_([NEW, SUPER])))
        await session.execute(delete(GoneChat).where(GoneChat.chat_id == NEW))
        await session.execute(delete(GroupMember).where(GroupMember.chat_id.in_([CHAT, NEW])))
        await session.execute(delete(GroupSettings).where(GroupSettings.chat_id == NEW))
        await session.commit()
    await engine.dispose()


if DB_URL:
    asyncio.run(with_database())
else:
    print("ℹ️  TEST_DATABASE_URL не задан — проверки с базой пропущены")

if failures:
    print(f"❌ Ошибок: {len(failures)} из {checks}")
    print("\n".join(failures))
    sys.exit(1)
print(f"✅ Все {checks} проверок участников-молчунов прошли.")
