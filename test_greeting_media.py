"""
Видео к приветствию новичков: отправка и загрузка через админку.

    python test_greeting_media.py                      — без базы проверяется только отправка
    TEST_DATABASE_URL=postgresql://… python test_greeting_media.py
"""

import asyncio
import os
import pathlib
import sys
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).parent))
DB_URL = os.getenv("TEST_DATABASE_URL", "")
os.environ.setdefault("DATABASE_URL", DB_URL or "postgresql+asyncpg://x:y@127.0.0.1:1/z")

from features.greeting import CAPTION_LIMIT, send_greeting  # noqa: E402

errors = []
checks = 0


def check(ok, what):
    global checks
    checks += 1
    if not ok:
        errors.append(what)


class FakeBot:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def _send(self, kind):
        async def send(chat_id, file, caption=None, **_):
            self.calls.append((kind, caption))
            if self.fail:
                raise RuntimeError("Bad Request: wrong file identifier")
            file_id = file if isinstance(file, str) else f"new-{kind}"
            return SimpleNamespace(
                video=SimpleNamespace(file_id=file_id) if kind == "video" else None,
                animation=SimpleNamespace(file_id=file_id) if kind == "animation" else None,
                photo=[SimpleNamespace(file_id=file_id)] if kind == "photo" else None,
                document=None,
            )
        return send

    def __getattr__(self, name):
        kinds = {"send_video": "video", "send_animation": "animation", "send_photo": "photo"}
        if name in kinds:
            return self._send(kinds[name])
        raise AttributeError(name)

    async def send_message(self, chat_id, text, **_):
        self.calls.append(("text", text))
        return SimpleNamespace(video=None, animation=None, photo=None, document=None)


async def sending():
    video = {"kind": "video", "file_id": "abc"}

    bot = FakeBot()
    await send_greeting(bot, -1, "Привет!", video)
    check(bot.calls == [("video", "Привет!")], f"короткий текст — подписью к видео: {bot.calls}")

    bot = FakeBot()
    long_text = "а" * (CAPTION_LIMIT + 1)
    await send_greeting(bot, -1, long_text, video)
    check(bot.calls == [("video", None), ("text", long_text)], f"длинный текст — видео, потом текст: {bot.calls}")

    bot = FakeBot(fail=True)
    await send_greeting(bot, -1, "Привет!", video)
    check(bot.calls[-1] == ("text", "Привет!"), f"видео не ушло — хотя бы текст: {bot.calls}")

    bot = FakeBot()
    await send_greeting(bot, -1, "Привет!", None)
    check(bot.calls == [("text", "Привет!")], f"без видео — только текст: {bot.calls}")

    bot = FakeBot()
    await send_greeting(bot, -1, "Привет!", {"kind": "animation", "file_id": "gif"})
    check(bot.calls == [("animation", "Привет!")], f"GIF: {bot.calls}")


async def admin_upload():
    """Загрузка из админки до сохранения в настройках группы и показа новичку."""
    from aiohttp.test_utils import TestClient, TestServer

    from database.database import init_db
    from features.greeting import greeting_media
    import webapp.admin_v2 as admin_v2
    from webapp.server import create_app

    await init_db()
    chat = -100777000222
    admin = {"id": 4242, "first_name": "Админ"}

    async def fake_perm(request, chat_id, permission):
        return admin, [{"chat_id": chat, "title": "Тест"}], "owner"

    admin_v2.require_perm = fake_perm
    bot = FakeBot()
    app = create_app(bot, "123:TEST")

    async with TestClient(TestServer(app)) as client:
        empty = await (await client.get(f"/api/admin/greeting_media?chat_id={chat}")).json()
        check(empty.get("media") is None, f"сначала ничего не прикреплено: {empty}")

        body = b"\x00" * (3 * 1024 * 1024)  # 3 МБ — больше старого лимита на запрос
        response = await client.post(
            f"/api/admin/greeting_media?chat_id={chat}&kind=video&name=hello.mp4",
            data=body, headers={"Content-Type": "video/mp4"},
        )
        data = await response.json()
        check(response.status == 200 and data.get("media", {}).get("kind") == "video", f"загрузка: {response.status} {data}")
        check(bot.calls and bot.calls[-1][0] == "video" and "Так новички увидят" in (bot.calls[-1][1] or ""),
              f"превью ушло админу: {bot.calls}")

        media = await greeting_media(chat)
        check(media and media["file_id"] == "new-video" and media["name"] == "hello.mp4", f"сохранено: {media}")

        too_big = await client.post(
            f"/api/admin/greeting_media?chat_id={chat}&kind=video",
            data=b"\x00" * (21 * 1024 * 1024), headers={"Content-Type": "video/mp4"},
        )
        check(too_big.status in (400, 413), f"больше 20 МБ не принимаем: {too_big.status}")

        bad = await client.post(f"/api/admin/greeting_media?chat_id={chat}&kind=exe", data=b"x")
        check(bad.status == 400, f"неизвестный тип: {bad.status}")

        bot.fail = True
        failed = await client.post(
            f"/api/admin/greeting_media?chat_id={chat}&kind=video", data=b"x", headers={"Content-Type": "video/mp4"},
        )
        check(failed.status == 400 and "Telegram" in (await failed.json()).get("error", ""), f"ошибка Telegram видна админу: {failed.status}")
        check((await greeting_media(chat))["file_id"] == "new-video", "неудачная загрузка не стирает прежнее видео")
        bot.fail = False

        removed = await client.post("/api/admin/greeting_media/delete", json={"chat_id": chat})
        check(removed.status == 200 and await greeting_media(chat) is None, "убрано")


async def main():
    await sending()
    if DB_URL:
        await admin_upload()
    else:
        print("   (без TEST_DATABASE_URL загрузка через админку не проверялась)")


asyncio.run(main())

if errors:
    print(f"❌ {len(errors)} из {checks} проверок не прошли:")
    print("\n".join("  " + e for e in errors))
    sys.exit(1)

print(f"✅ Все {checks} проверок видео в приветствии прошли.")
