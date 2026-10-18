"""
Реклама от чужих ботов.

Музыкальный бот присылает трек, а вместе с ним — рекламу. Админ
перечисляет таких ботов в настройках, и Мара удаляет всё, что они
пишут, кроме самих файлов: аудио, голосовых и видео.

Чужие боты обычно невидимы для Мары: Telegram показывает их сообщения
только ботам с режимом Bot-to-Bot Communication (@BotFather), которые
админы группы и с выключенным Group Privacy.
"""

import logging

from aiogram import Router
from aiogram.types import Message

import audit

from settings.store import get_text


logger = logging.getLogger("maruska.bot_ads")

router = Router(name="bot_ads")

# Чьи сообщения уже отметили в логе: видно, что Bot-to-Bot заработал
_seen: set[tuple[int, int]] = set()


def ad_bots(chat_id: int) -> set[str]:
    raw = get_text(chat_id, "ad_bots") or ""
    names = (part.strip().lstrip("@").lower() for part in raw.replace(";", ",").replace("\n", ",").split(","))
    return {name for name in names if name}


def is_payload(message: Message) -> bool:
    """То, ради чего бота держат в группе: сам трек или видео."""
    if message.audio or message.voice or message.video or message.video_note:
        return True
    mime = (message.document.mime_type or "") if message.document else ""
    return mime.startswith(("audio/", "video/"))


def should_delete(message: Message, bots: set[str]) -> bool:
    author = message.from_user
    if author is None or not author.is_bot or not author.username:
        return False
    return author.username.lower() in bots and not is_payload(message)


def _note_seen(message: Message) -> None:
    author = message.from_user
    key = (message.chat.id, author.id)
    if key not in _seen and len(_seen) < 5000:
        _seen.add(key)
        logger.info("BOT MSG: вижу сообщения @%s в чате %s", author.username, message.chat.id)


def is_ad(message: Message) -> bool:
    """
    Фильтр: только сообщения ботов из списка группы. Остальное идёт дальше —
    анонимные админы и посты канала тоже приходят «от бота», их не трогаем.
    """
    if message.chat.type not in ("group", "supergroup") or not message.from_user or not message.from_user.is_bot:
        return False
    _note_seen(message)
    return should_delete(message, ad_bots(message.chat.id))


@router.message(is_ad)
async def other_bot_ad(message: Message):
    author = message.from_user

    try:
        await message.delete()
    except Exception as error:
        logger.warning("BOT ADS: не удалила сообщение @%s в чате %s: %s", author.username, message.chat.id, error)
        return

    logger.info("BOT ADS: удалила рекламу @%s в чате %s", author.username, message.chat.id)
    audit.count(message.chat.id, "deleted")
