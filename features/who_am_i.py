"""
«Мара, кто я?» — карточка человека, как /profile: брак, уровень, рейтинг,
место, алмазы, сообщения, игры, оценки. У каждого своя.

    Мара, кто я? / кто я такой? / что ты обо мне знаешь? / расскажи обо мне
    Мара, кто @ник? / ответом на сообщение: «Мара, кто это?»

«Мара, кто я сегодня?» — это уже «кто сегодня» (случайный участник).
"""

import logging
import re
from html import escape

from aiogram import Router
from aiogram.types import Message

import botcontext
from botcontext import TRIGGER_RE, display_name_of, is_addressed


logger = logging.getLogger("maruska.who_am_i")

router = Router(name="who_am_i")

_ABOUT_ME = re.compile(
    r"^\W*(?:кто\s+я(?:\s+так(?:ой|ая))?|что\s+ты\s+(?:знаешь\s+)?обо\s+мне(?:\s+знаешь)?|расскажи\s+обо\s+мне"
    r"|какой\s+я|какая\s+я)\W*$",
    re.IGNORECASE,
)
_ABOUT_OTHER = re.compile(r"^\W*кто\s+(?:это|он|она|так(?:ой|ая))(?:\s+так(?:ой|ая))?\W*$", re.IGNORECASE)
_ABOUT_MENTION = re.compile(r"^\W*(?:кто|что\s+знаешь\s+(?:о|про))\s+(?:так(?:ой|ая)\s+)?@(\w{4,32})\W*$", re.IGNORECASE)


def parse(message: Message) -> tuple[str, str | None] | None:
    """('me' | 'reply' | 'mention', @ник) или None, если это не такой вопрос."""
    text = message.text or ""
    if not text or text.startswith("/"):
        return None
    body = TRIGGER_RE.sub(" ", text, count=1).replace(",", " ")
    if _ABOUT_ME.match(body):
        return "me", None
    found = _ABOUT_MENTION.match(body)
    if found:
        return "mention", found.group(1)
    reply = message.reply_to_message
    if _ABOUT_OTHER.match(body) and reply and reply.from_user and not reply.from_user.is_bot:
        return "reply", None
    return None


def is_who_am_i(message: Message) -> bool:
    if message.chat.type not in ("group", "supergroup"):
        return False
    if message.from_user is None or message.from_user.is_bot:
        return False
    return parse(message) is not None and is_addressed(message)


async def _resolve(message: Message, kind: str, username: str | None):
    """Про кого спрашивают: (id, имя) или None."""
    if kind == "me":
        return message.from_user.id, display_name_of(message.from_user)
    if kind == "reply":
        target = message.reply_to_message.from_user
        return target.id, display_name_of(target)
    from database.repository import get_user_by_username, member_name

    user = await get_user_by_username(username)
    if user is None:
        return None
    return user.telegram_id, await member_name(message.chat.id, user.telegram_id)


@router.message(is_who_am_i)
async def who_am_i(message: Message):
    from features.rating import profile_card

    kind, username = parse(message)
    target = await _resolve(message, kind, username)
    if target is None:
        await message.reply(f"🤷 Не знаю такого: @{escape(username or '')}. Пусть сначала напишет в чат.")
        return
    telegram_id, name = target
    if telegram_id == botcontext.BOT_ID:
        await message.reply("🔮 Это я, Маруська. Самая умная и скромная в этом чате 😌")
        return

    card = await profile_card(message.chat.id, telegram_id, name, create=telegram_id == message.from_user.id)
    if card is None:
        await message.reply(f"🤷 Про <b>{escape(name)}</b> пока ничего нет — пусть напишет в чат.")
        return
    await message.reply(card)
