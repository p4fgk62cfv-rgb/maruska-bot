"""
/help — только команды для людей; /helpadmin — команды модерации,
в группе уходят админу в личку, остальным ничего.
Запуск:  python test_help_admin.py
"""

import asyncio
import os
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).parent))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:y@127.0.0.1:1/z")

from features import basic  # noqa: E402
import settings.handler as sh  # noqa: E402

errors = []

for word in ("/warn", "/mute", "/ban", "/kick", "/lock", "/settings", "/tban", "/delete", "/welcomevideo"):
    if word in basic.HELP_TEXT:
        errors.append(f"в /help для людей есть {word}")
    if word not in basic.ADMIN_HELP_TEXT:
        errors.append(f"в /helpadmin нет {word}")
for word in ("/bonus", "/fishing", "/arena", "/срок"):
    if word not in basic.HELP_TEXT:
        errors.append(f"в /help нет {word}")

basic.NOTICE_TTL = 0


class Bot:
    def __init__(self, dm_ok=True):
        self.dm, self.dm_ok = [], dm_ok

    async def send_message(self, chat_id, text):
        if not self.dm_ok:
            raise RuntimeError("bot can't initiate conversation")
        self.dm.append((chat_id, text))


def msg(bot, kind="supergroup", uid=7):
    said, deleted = [], []

    async def answer(text):
        said.append(text)
        return types.SimpleNamespace(delete=lambda: asyncio.sleep(0))

    async def delete():
        deleted.append(True)

    m = types.SimpleNamespace(
        bot=bot, answer=answer, delete=delete,
        chat=types.SimpleNamespace(id=-100 if kind != "private" else uid, type=kind),
        from_user=types.SimpleNamespace(id=uid, is_bot=False, first_name="Аня", username=None),
    )
    return m, said, deleted


async def main():
    async def admin(event, bot):
        return True

    async def member(event, bot):
        return False

    sh.is_admin = admin
    bot = Bot()
    m, said, deleted = msg(bot)
    await basic.admin_help_handler(m)
    if bot.dm != [(7, basic.ADMIN_HELP_TEXT)]:
        errors.append(f"админу в личку: {bot.dm}")
    if not deleted or not said or "/warn" in said[0] or "личку" not in said[0]:
        errors.append(f"в группе только короткое «в личку», команда удалена: {said} {deleted}")

    bot = Bot(dm_ok=False)
    m, said, _ = msg(bot)
    await basic.admin_help_handler(m)
    if not said or "Старт" not in said[0] or "/warn" in said[0]:
        errors.append(f"личка закрыта — просим нажать «Старт»: {said}")

    sh.is_admin = member
    bot = Bot()
    m, said, deleted = msg(bot)
    await basic.admin_help_handler(m)
    if bot.dm or said or not deleted:
        errors.append(f"не админ: ничего не видит, команда удалена: {bot.dm} {said}")

    sh.is_owner = lambda uid: uid == 1
    m, said, _ = msg(Bot(), kind="private", uid=1)
    await basic.admin_help_handler(m)
    if said != [basic.ADMIN_HELP_TEXT]:
        errors.append("главному админу в личке — список")
    m, said, _ = msg(Bot(), kind="private", uid=2)
    await basic.admin_help_handler(m)
    if not said or "/warn" in said[0]:
        errors.append(f"обычному человеку в личке — без команд модерации: {said}")
    await asyncio.sleep(0.01)


asyncio.run(main())

if errors:
    print("❌ " + "\n❌ ".join(errors))
    sys.exit(1)
print("✅ /help и /helpadmin: все проверки прошли.")
