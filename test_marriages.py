"""
Браки: один на все группы, «Мара, пары», свидетельство о браке (картинкой).

    TEST_DATABASE_URL=postgresql://… python test_marriages.py
"""

import asyncio
import os
import pathlib
import random
import sys
import types
from datetime import datetime, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).parent))
DB_URL = os.getenv("TEST_DATABASE_URL", "")
os.environ.setdefault("DATABASE_URL", DB_URL or "postgresql+asyncpg://x:y@127.0.0.1:1/z")

import botcontext  # noqa: E402
from features import marriage_certificate as mc  # noqa: E402
from features import social  # noqa: E402

errors = []


def check(ok, what):
    if not ok:
        errors.append(what)


# «Мара, пары» — только после обращения и только сам запрос
social.is_enabled = lambda chat_id, key: True


def group_msg(text):
    return types.SimpleNamespace(text=text, chat=types.SimpleNamespace(id=-1, type="supergroup"))


for text, want in [("Мара, пары", True), ("мара пары?", True), ("Маруська, список пар", True),
                   ("Мара, браки", True), ("пары", False), ("Мара, пара дня", False),
                   ("Мара, какие пары красивые", False), ("/marriages", False)]:
    check(social.is_couples_request(group_msg(text)) == want, f"«{text}» → {not want}")

# @ник в списке — ссылкой, чтобы список никого не уведомлял
person = social._person("Вася <3", "vasya")
check(person == 'Вася &lt;3 (<a href="https://t.me/vasya">@vasya</a>)', f"имя с ником: {person}")
check(social._person("Юля", None) == "Юля", "имя без ника")

# Свидетельство рисуется картинкой, длинные имена не ломают
cert = {"number": 7, "name1": "Александра-Виктория Длинноимённая", "name2": "Юля",
        "tag1": "@alexandra", "tag2": None, "since": "2026-10-20T12:00:00", "group": "Flash"}
image = mc.jpeg_bytes(cert)
check(image[:3] == b"\xff\xd8\xff" and 100_000 < len(image) < 2_000_000, f"картинка: {len(image)} байт")
check(mc.number_text(7) == "№ МР-000007", "номер")
check(mc.date_ru(datetime(2026, 3, 8)) == "8 марта 2026 года", "дата")

# Стилизованные ники Telegram — в обычные буквы, эмодзи прочь
for raw, want in [("🦋𝐋𝐞𝐬𝐲𝐚🦋", "Lesya"), ("STANISLAV", "Stanislav"), ("Юля 💕", "Юля"),
                  ("✨✨", "Супруг"), ("Ａｎｎａ", "Anna"), ("Анна-Мария", "Анна-Мария")]:
    check(mc.clean_name(raw) == want, f"имя «{raw}» → {mc.clean_name(raw)!r}, ждали {want!r}")


async def scenario():
    from sqlalchemy import delete

    from database.database import init_db, session_scope
    from database.models import GroupMember, Marriage, User
    from database import repository as repo

    await init_db()

    base = random.randint(10**9, 2 * 10**9)
    a, b, c, d = base + 1, base + 2, base + 3, base + 4
    chat_a, chat_b = -base, -base - 1

    async with session_scope() as session:
        session.add_all([
            GroupMember(chat_id=chat_a, telegram_id=a, display_name="Вася"),
            GroupMember(chat_id=chat_a, telegram_id=b, display_name="Юля"),
            GroupMember(chat_id=chat_b, telegram_id=a, display_name="Василий"),
            GroupMember(chat_id=chat_b, telegram_id=c, display_name="Оля"),
            User(telegram_id=a, username="vasya_test", first_name="Вася"),
        ])
        await session.commit()

    try:
        # Брак один на все группы
        marriage_id = await repo.create_marriage(chat_a, a, b)
        check(isinstance(marriage_id, int), "брак заключён")
        check(await repo.create_marriage(chat_b, a, c) is None, "второй брак в другой группе запрещён")
        found = await repo.active_marriage(chat_b, a)
        check(found is not None and found.id == marriage_id, "в другой группе видно, что женат")

        # Список пар у каждой группы свой: пара из A есть в A и нет в B
        couples = await repo.list_marriages(chat_a)
        mine = [x for x in couples if x["id"] == marriage_id]
        check(len(mine) == 1 and mine[0]["name1"] == "Вася" and mine[0]["name2"] == "Юля"
              and mine[0]["username1"] == "vasya_test", f"пары группы A: {couples}")
        check(not [x for x in await repo.list_marriages(chat_b) if x["id"] == marriage_id], "в группе B пары из A нет")
        check(await repo.member_name(chat_b, b) == "Юля", "имя из другой группы")

        # Снимок для свидетельства делается один раз и не меняется
        snap = await social.certificate_of(marriage_id, "Группа A")
        check(snap["name1"] == "Вася" and snap["tag1"] == "@vasya_test" and snap["group"] == "Группа A"
              and snap["number"] == marriage_id, f"снимок: {snap}")
        again = await social.certificate_of(marriage_id, "Другая группа")
        check(again == snap, "снимок не меняется")

        # Кнопка «Свидетельство»: первый раз картинка рисуется, дальше — по file_id
        sent = []

        async def answer_photo(photo, caption=None):
            sent.append(photo)
            return types.SimpleNamespace(photo=[types.SimpleNamespace(file_id="small"), types.SimpleNamespace(file_id="FILE123")])

        async def answer(*args, **kwargs):
            return None

        callback = types.SimpleNamespace(
            data=f"mcert:{marriage_id}", answer=answer,
            message=types.SimpleNamespace(answer_photo=answer_photo),
        )
        await social.certificate_download(callback)
        await social.certificate_download(callback)
        check(len(sent) == 2 and not isinstance(sent[0], str) and sent[1] == "FILE123", f"скачивание: {sent}")

        # После смены оформления старую картинку не отдаём — рисуем заново
        await repo.save_marriage_certificate(marriage_id, file_id="v0:OLD")
        sent.clear()
        await social.certificate_download(callback)
        check(len(sent) == 1 and not isinstance(sent[0], str), f"старая картинка перерисована: {sent}")

        # Развод из любой группы
        check(await repo.end_marriage(chat_b, b) == (a, b), "развод из другой группы")
        check(await repo.active_marriage(chat_a, a) is None, "после развода свободен")

        # Старые браки из разных групп: остаётся самый ранний
        now = datetime.utcnow()
        async with session_scope() as session:
            session.add_all([
                Marriage(chat_id=chat_a, user1=a, user2=b, since=now - timedelta(days=10)),
                Marriage(chat_id=chat_b, user1=a, user2=c, since=now - timedelta(days=5)),
                Marriage(chat_id=chat_b, user1=c, user2=d, since=now - timedelta(days=1)),
            ])
            await session.commit()
        chat_c, chat_d = -base - 2, -base - 3
        async with session_scope() as session:
            session.add_all([
                # Та же пара зарегистрирована и в группе B — это не второй брак
                Marriage(chat_id=chat_b, user1=b, user2=a, since=now - timedelta(days=3)),
            ])
            await session.commit()
        ended = await repo.dedupe_marriages()
        ended_pairs = {(x[1], x[2]) for x in ended}
        check((a, c) in ended_pairs and (a, b) not in ended_pairs and (b, a) not in ended_pairs,
              f"расторгнуты только чужие повторы: {ended}")
        left = await repo.active_marriage(None, a)
        check(left is not None and {left.user1, left.user2} == {a, b}, "остался самый ранний брак")
        check(set(left.chats or []) == {chat_b}, f"группа той же пары добавлена к браку: {left.chats}")
        for chat in (chat_a, chat_b):
            check(any(x["id"] == left.id for x in await repo.list_marriages(chat)), f"пара видна в группе {chat}")
        check(not any(x["id"] == left.id for x in await repo.list_marriages(chat_d)), "в чужой группе пары нет")

        # Супруги делают предложение друг другу в новой группе — брак виден и там
        check(await repo.register_marriage_here(chat_d, b, a) == left.id, "регистрация в новой группе")
        check(any(x["id"] == left.id for x in await repo.list_marriages(chat_d)), "теперь видна и в новой группе")
        check(await repo.register_marriage_here(chat_d, a, c) is None, "чужая пара не регистрируется")
        check(await repo.dedupe_marriages() == [], "повторный запуск ничего не меняет")

        # Разовый перенос пары в группу по названию и @никам
        from database.models import GroupSettings

        title = "꧁ 𝑫𝑰𝑨𝑴𝑶𝑵𝑫" + str(base) + " ꧂"
        async with session_scope() as session:
            session.add(GroupSettings(chat_id=chat_d, title=title, values={}))
            session.add(User(telegram_id=b, username="Yulia_Test", first_name="Юля"))
            await session.commit()
        note = await repo.move_marriage(("vasya_test", "yulia_test"), f"diamond{base}")
        moved = await repo.active_marriage(None, a)
        check(moved.chat_id == chat_d and not moved.chats and "перенесён" in note, f"перенос: {note}")
        check([x["id"] for x in await repo.list_marriages(chat_d)] == [moved.id], "пара в новой группе")
        check(not any(x["id"] == moved.id for x in await repo.list_marriages(chat_b)), "из других групп убрана")
        check("уже в группе" in await repo.move_marriage(("vasya_test", "yulia_test"), f"diamond{base}"), "повтор — без изменений")
        check("не найдена" in await repo.move_marriage(("vasya_test", "yulia_test"), "нет-такой-группы"), "нет группы")
    finally:
        async with session_scope() as session:
            await session.execute(delete(Marriage).where(Marriage.user1.in_([a, b, c, d]) | Marriage.user2.in_([a, b, c, d])))
            await session.execute(delete(GroupMember).where(GroupMember.telegram_id.in_([a, b, c, d])))
            await session.execute(delete(User).where(User.telegram_id.in_([a, b, c, d])))
            from database.models import GroupSettings
            await session.execute(delete(GroupSettings).where(GroupSettings.chat_id.in_([chat_a, chat_b, -base - 2, -base - 3])))
            await session.commit()


if DB_URL:
    botcontext.BOT_ID = 777
    asyncio.run(scenario())
else:
    print("⚠️ Без TEST_DATABASE_URL — только проверки без базы")

if errors:
    print("❌ " + "\n❌ ".join(errors))
    sys.exit(1)
print("✅ Браки и свидетельства: все проверки прошли.")
