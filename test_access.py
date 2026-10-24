"""
Доступ групп к функциям Мары (решает владелец): новые группы закрыты, знакомые — открыты.

    TEST_DATABASE_URL=postgresql://… python test_access.py
"""

import asyncio
import os
import pathlib
import random
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).parent))
DB_URL = os.getenv("TEST_DATABASE_URL", "")
os.environ.setdefault("DATABASE_URL", DB_URL or "postgresql+asyncpg://x:y@127.0.0.1:1/z")

from settings import access  # noqa: E402

errors = []


def check(ok, what):
    if not ok:
        errors.append(what)


def msg(chat_id, text=""):
    return types.SimpleNamespace(chat=types.SimpleNamespace(id=chat_id), text=text)


# Без загрузки (ошибка базы при старте) ничего не запирается
check(access.allowed(-100500, "arena"), "до загрузки — всё можно")

# «Заглушка» отвечает только на команды этого бота и обращения к Маре
import botcontext  # noqa: E402
from features import locked  # noqa: E402

botcontext.BOT_USERNAME = "BotMaruska_bot"
for text, want in [("/game", True), ("/game@BotMaruska_bot", True), ("/game@other_bot", False),
                   ("Мара, привет", True), ("привет, Мара", False), ("просто текст", False)]:
    check(locked._ours(msg(-1, text)) is want, f"заглушка: «{text}» → ждали {want}")


async def scenario():
    from sqlalchemy import delete

    from database.database import init_db, session_scope
    from database.models import GroupMember, GroupSettings
    from database.repository import get_group_settings, set_group_setting

    await init_db()
    base = random.randint(10**9, 2 * 10**9)
    old_group, known_group, new_group = -base, -base - 1, -base - 2
    flag_before = (await get_group_settings(0)).get(access.FLAG)
    try:
        async with session_scope() as session:
            session.add(GroupSettings(chat_id=old_group, title="Старая", values={"digest": True}))
            session.add(GroupMember(chat_id=known_group, telegram_id=base, display_name="Кто-то"))
            await session.commit()
        # Первый запуск: всем знакомым группам — всё
        await set_group_setting(0, access.FLAG, False)
        await access.load()
        for chat in (old_group, known_group):
            check(access.allowed(chat, "arena") and access.allowed(chat, "chat"), f"знакомая группа {chat} — всё открыто")
            check((await get_group_settings(chat)).get(access.KEY) == {"all": True}, f"доступ {chat} сохранён в базе")
        check((await get_group_settings(0)).get(access.FLAG) is True, "флаг первого запуска поставлен")

        # Новая группа после этого — закрыта
        check(not access.allowed(new_group, "arena") and not access.allowed(new_group, "fishing"), "новая группа закрыта")
        check(access.entry(new_group) == {"all": False, "modules": []}, "новая группа: ничего не открыто")
        check(access.allowed(12345, "arena"), "в личке ограничений нет")

        # Владелец открывает Арену — только её
        got = await access.set_access(new_group, module="arena", on=True)
        check(got == {"all": False, "modules": ["arena"]}, f"открыта Арена: {got}")
        check(access.allowed(new_group, "arena") and not access.allowed(new_group, "fishing"), "Арена — да, рыбалка — нет")
        # Перезапуск бота: доступ читается из базы, второй раз «всё всем» не раздаётся
        await access.load()
        check(access.entry(new_group) == {"all": False, "modules": ["arena"]}, "после перезапуска — то же")

        # Фильтр роутера: сообщение и кнопка (callback) этой группы
        flt = access.router_filter("fishing")
        check(not flt(msg(new_group)), "фильтр: рыбалка в новой группе — нет")
        check(access.router_filter("arena")(types.SimpleNamespace(message=msg(new_group))), "фильтр кнопки: Арена — да")
        check(flt(msg(777)), "фильтр: личка — да")

        # Всё разом и обратно
        check((await access.set_access(new_group, everything=True))["all"], "всё разрешено")
        check(access.allowed(new_group, "fishing"), "после «всё» — и рыбалка")
        check(await access.set_access(new_group, everything=False) == {"all": False, "modules": []}, "«всё» выключено — с нуля")
        # Включили по одному все модули — это и есть «всё»
        for module in access.MODULES:
            last = await access.set_access(new_group, module=module, on=True)
        check(last == {"all": True, "modules": []}, f"все модули по одному = всё: {last}")

        # Группа стала супергруппой — доступ переехал
        access.move(new_group, new_group - 5)
        check(access.allowed(new_group - 5, "arena") and not access.allowed(new_group, "arena"), "доступ переехал на новый ID")
    finally:
        async with session_scope() as session:
            await session.execute(delete(GroupSettings).where(GroupSettings.chat_id.in_([old_group, known_group, new_group])))
            await session.execute(delete(GroupMember).where(GroupMember.chat_id == known_group))
            await session.commit()
        await set_group_setting(0, access.FLAG, flag_before if flag_before is not None else True)


if DB_URL:
    asyncio.run(scenario())
else:
    print("ℹ️  TEST_DATABASE_URL не задан — сценарий с базой пропущен")

if errors:
    print("❌ " + "\n❌ ".join(errors))
    sys.exit(1)
print("✅ Доступ групп: все проверки прошли.")
