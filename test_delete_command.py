"""
/delete ответом на сообщение: удаляет админ, остальным — нельзя.
Запуск:  python test_delete_command.py
"""

import asyncio
import os
import pathlib
import sys
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).parent))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:y@127.0.0.1:1/z")

import features.moderation as moderation  # noqa: E402

errors = []
checks = 0


def check(ok, what):
    global checks
    checks += 1
    if not ok:
        errors.append(what)


class Msg:
    def __init__(self, name, author, reply=None, fail=None, log=None):
        self.name, self.from_user, self.reply_to_message = name, author, reply
        self.chat = SimpleNamespace(id=-100777, type="supergroup")
        self.fail, self.log = fail, log if log is not None else []
        self.bot = None

    async def delete(self):
        if self.fail:
            raise RuntimeError(self.fail)
        self.log.append(("deleted", self.name))

    async def answer(self, text, **_):
        self.log.append(("notice", text))
        return Msg("notice", None, log=self.log)


def user(uid, bot=False):
    return SimpleNamespace(id=uid, is_bot=bot, first_name=f"U{uid}", username=None)


async def run(is_admin, reply_author=None, fail=None):
    log = []

    async def fake_admin(message):
        return is_admin

    moderation._is_chat_admin = fake_admin
    moderation._record = lambda *a, **k: log.append(("record", a[1]))
    reply = Msg("target", reply_author, fail=fail, log=log) if reply_author else None
    await moderation.delete_command(Msg("command", user(1), reply=reply, log=log))
    return log


async def main():
    mara = user(777, bot=True)

    log = await run(True, mara)
    check(("deleted", "target") in log and ("deleted", "command") in log, f"админ удаляет сообщение Мары и команду: {log}")
    check(not any(kind == "notice" for kind, _ in log), f"после удаления лишних сообщений нет: {log}")

    log = await run(True, user(5))
    check(("deleted", "target") in log, f"админ удаляет и чужое сообщение: {log}")

    log = await run(False, mara)
    check(("deleted", "target") not in log, f"не админ ничего не удаляет: {log}")
    check(any(kind == "notice" and "администратор" in text for kind, text in log), f"не админу объяснили: {log}")

    log = await run(True, None)
    check(any(kind == "notice" and "Ответь" in text for kind, text in log), f"без ответа — подсказка: {log}")

    log = await run(True, user(5), fail="Bad Request: message can't be deleted")
    check(any(kind == "notice" and "Удаление сообщений" in text for kind, text in log), f"нет прав — понятная причина: {log}")


asyncio.run(main())

if errors:
    print(f"❌ {len(errors)} из {checks} проверок не прошли:")
    print("\n".join("  " + e for e in errors))
    sys.exit(1)

print(f"✅ Все {checks} проверок /delete прошли.")
