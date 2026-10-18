"""
Реклама чужих ботов: удаляется всё от ботов из списка, кроме файлов.
Запуск:  python test_bot_ads.py
"""

import asyncio
import os
import pathlib
import sys
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).parent))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:y@127.0.0.1:1/z")

from settings import store  # noqa: E402
from features.bot_ads import ad_bots, is_ad, other_bot_ad  # noqa: E402

errors = []
checks = 0


def check(ok, what):
    global checks
    checks += 1
    if not ok:
        errors.append(what)


CHAT = -100555
store.prime(CHAT, {"ad_bots": "@Music_Bot, other_bot"})
store.prime(-100556, {})


def msg(username="music_bot", is_bot=True, chat=CHAT, text="БЛЕФ🃏, Мы создали бота…", **media):
    fields = {k: None for k in ("audio", "voice", "video", "video_note", "document")}
    fields.update(media)
    deleted = []

    async def delete():
        deleted.append(True)

    return SimpleNamespace(
        from_user=SimpleNamespace(id=hash(username) % 10**6, is_bot=is_bot, username=username),
        chat=SimpleNamespace(id=chat, type="supergroup"), text=text, delete=delete, _deleted=deleted, **fields,
    )


check(ad_bots(CHAT) == {"music_bot", "other_bot"}, f"список ботов: {ad_bots(CHAT)}")
check(is_ad(msg()), "реклама бота из списка удаляется")
check(is_ad(msg(username="OTHER_BOT")), "регистр username не важен")
check(not is_ad(msg(audio=SimpleNamespace())), "аудио остаётся")
check(not is_ad(msg(video=SimpleNamespace())), "видео остаётся")
check(not is_ad(msg(document=SimpleNamespace(mime_type="audio/mpeg"))), "mp3 файлом остаётся")
check(is_ad(msg(document=SimpleNamespace(mime_type="image/png"))), "картинка-реклама удаляется")
check(not is_ad(msg(username="captcha_bot")), "чужой бот не из списка — не трогаем")
check(not is_ad(msg(username="GroupAnonymousBot")), "анонимный админ — не трогаем")
check(not is_ad(msg(is_bot=False)), "люди — не трогаем")
check(not is_ad(msg(chat=-100556)), "в группе без списка — не трогаем")

m = msg()
asyncio.run(other_bot_ad(m))
check(m._deleted == [True], "обработчик удаляет сообщение")

if errors:
    print(f"❌ {len(errors)} из {checks} проверок не прошли:")
    print("\n".join("  " + e for e in errors))
    sys.exit(1)

print(f"✅ Все {checks} проверок рекламы ботов прошли.")
