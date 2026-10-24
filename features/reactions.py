"""
Реакции Мары на сообщения.

Мара сама ставит реакцию: 🤣 — на ржач, ❤ — на милое, 🍾 — когда
кто-то кого-то угощает водкой, 🥰 — на цветы и котиков. Не на каждое
сообщение: по шансу из настроек и не чаще раза в несколько секунд,
чтобы не выглядело как спам. На ответ самой Маре стикером, гифкой или
смайлом без слов реакцию не ставит.

Стоит внешней мидлварью: действия, игры и команды перехватывают
сообщение раньше общего обработчика, а реакция нужна и на них.
"""

import asyncio
import logging
import random
import re
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, ReactionTypeEmoji, TelegramObject

from botcontext import is_wordless_reply_to_bot
from settings.store import get_number, is_enabled


logger = logging.getLogger("maruska.reactions")

# Только эмодзи, которые Telegram разрешает в реакциях
ACTION_CATEGORY = {
    "alcohol": ("🍾", "🥴", "🔥"),
    "drink": ("🔥", "❤", "👌"),
    "food": ("🔥", "😍", "👌"),
    "sweet": ("🍓", "🥰", "😍"),
    "fruit": ("🍓", "🍌", "👌"),
    "flower": ("🥰", "😍", "💘"),
    "gift": ("🎉", "🤩", "🥰"),
    "pet": ("🥰", "🦄", "😍"),
    "library": ("🔥", "❤", "😁"),
}

ACTION_KEY = {
    "beer": ("🍾", "🥴", "🔥"),
    "vodka": ("🥴", "🍾", "😈"),
    "moonshine": ("🥴", "🤯", "😈"),
    "champagne": ("🍾", "🎉", "🤩"),
    "coffee": ("⚡", "❤", "👌"),
    "energy": ("⚡", "🤯"),
    "cactus": ("🌚", "😁"),
    "banana": ("🍌", "🌚", "😁"),
    "strawberry": ("🍓", "🥰"),
    "hotdog": ("🌭", "😁"),
    "sausages": ("🌭", "🔥"),
    "crown": ("🏆", "🤩", "😇"),
    "cup_award": ("🏆", "👏"),
    "medal": ("🏆", "👏"),
    "money": ("🤩", "💯"),
    "madhouse": ("🤡", "🤪", "😁"),
    "ambulance": ("🙏", "😱"),
    "taxi": ("🆒", "👌"),
    "firefighters": ("🔥", "❤‍🔥"),
    "hug": ("🤗", "🥰", "❤"),
    "support": ("🤗", "❤", "🙏"),
    "cover": ("🤗", "🥰"),
    "lull": ("😴", "🥰"),
    "carry": ("🥰", "🤗"),
    "pat": ("🥰", "😇"),
    "kiss": ("💋", "😘", "😍"),
    "wink": ("😈", "🌚"),
    "tickle": ("🤣", "😁"),
    "party": ("🎉", "🍾", "🔥"),
    "congratulations": ("🎉", "🍾", "👏"),
    "praise": ("👏", "💯", "🔥"),
    "scold": ("🌚", "😈"),
    "highfive": ("🤝", "🔥"),
    "handshake": ("🤝", "🫡"),
    "sing": ("🎉", "🤩"),
    "dance": ("🔥", "🤩"),
    "gym": ("💯", "🔥"),
    "game": ("👾", "🔥"),
    "photo": ("😎", "🔥"),
    "selfie": ("😎", "😍"),
    "sea": ("🐳", "😎"),
    "fishing": ("🐳", "😁"),
    "wake": ("🥱", "😴"),
}

PAIR_DEFAULT = ("❤", "🔥", "👏")

LAUGH = (
    "🤣", "🤣", "😁",
    re.compile(
        r"(?:"
        r"\b[ах]*(?:ха|хах|ахах|хех|хих|пх)[ахеип]*\b"
        r"|\bржу\b|\bржак|\bржач|\bугар|\bору\b|\bорну|\bорнул|\bлол\b|\blol\b|\blmao\b"
        r"|😂|🤣|😆|😹|\){3,}"
        r")",
        re.IGNORECASE,
    ),
)
CONGRATS = (
    "🎉", "🍾", "👏",
    re.compile(r"(поздравля|с (?:днём|днем) рождени|\bс др\b|\bура+\b|🎉|🥳|🎂)", re.IGNORECASE),
)
SAD = (
    "🤗", "❤", "🙏",
    re.compile(r"(грустн|печальн|\bплачу\b|тоскл|одиноко|\bустал[аи]?\b|всё плохо|все плохо|😢|😭|😞|💔)", re.IGNORECASE),
)
NIGHT = (
    "😴", "🌚", "😇",
    re.compile(r"(спокойной ночи|доброй ночи|сладких снов|\bспать пора\b|\bспокиночи\b)", re.IGNORECASE),
)
CUTE = (
    "❤", "🥰", "😍",
    re.compile(
        r"(\bлюблю\b|обожаю|\bмил(?:ый|ая|о|ота|ашк|ые)\b|котик|котёнок|котенок|зайк|солнышк|красотк|красотищ"
        r"|обнимаю|целую|\bняша|❤|♥|🥰|😍|😘|💕|💖|💗|🤗|😻)",
        re.IGNORECASE,
    ),
)
THANKS = (
    "🙏", "❤", "🤗",
    re.compile(r"(\bспасибо\b|\bспасиб|благодар)", re.IGNORECASE),
)

TEXT_RULES = (LAUGH, CONGRATS, SAD, NIGHT, CUTE, THANKS)
PHOTO = ("🔥", "😍", "👍")

# Не чаще раза в столько секунд в одном чате
COOLDOWN = 8.0
_last: dict[int, float] = {}


def pick_for_action(action) -> str | None:
    options = ACTION_KEY.get(action.key) or ACTION_CATEGORY.get(action.category)
    if options is None and action.category == "pair":
        options = PAIR_DEFAULT
    return random.choice(options) if options else None


def pick_for_text(text: str) -> str | None:
    for *options, pattern in TEXT_RULES:
        if pattern.search(text):
            return random.choice(options)
    return None


def has_target(message: Message) -> bool:
    reply = message.reply_to_message
    if reply is not None and reply.from_user is not None:
        return True
    return "@" in (message.text or "")


def decide(message: Message) -> tuple[str, int] | None:
    """(реакция, шанс в процентах) или None, если реагировать не на что."""
    # Ответ Маре стикером, гифкой или смайлом — не отвечаем реакцией на реакцию
    if is_wordless_reply_to_bot(message):
        return None

    chance = get_number(message.chat.id, "reaction_chance")
    text = message.text or message.caption or ""

    if message.text and not text.startswith("/"):
        from actions import custom

        action = custom.resolve(message.chat.id, message.text)
        if action is not None and has_target(message):
            emoji = pick_for_action(action)
            # Угощения — главный повод: на них Мара реагирует заметно чаще
            return (emoji, min(100, chance + 35)) if emoji else None

    if text and not text.startswith("/"):
        emoji = pick_for_text(text)
        if emoji:
            return emoji, chance

    if message.photo or message.video or message.animation:
        return random.choice(PHOTO), chance // 3

    return None


def _ready(chat_id: int, now: float) -> bool:
    return now - _last.get(chat_id, float("-inf")) >= COOLDOWN


async def _react(message: Message, emoji: str) -> None:
    # Небольшая пауза — будто Мара прочитала и улыбнулась
    await asyncio.sleep(random.uniform(0.8, 2.5))
    try:
        await message.react([ReactionTypeEmoji(emoji=emoji)])
    except Exception as error:
        # В группе могут быть запрещены реакции или эта конкретная — не страшно
        logger.info("REACTION %s: %s", emoji, error)


def _chat_allowed(chat_id: int) -> bool:
    """Реакции — часть модуля «Разговор с Марой» (доступ решает владелец)."""
    from settings import access

    return access.allowed(chat_id, "chat")


class ReactionsMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable[Any]],
        event: TelegramObject,
        data: dict,
    ) -> Any:
        result = await handler(event, data)

        try:
            if (
                isinstance(event, Message)
                and event.chat.type in ("group", "supergroup")
                and event.from_user is not None
                and not event.from_user.is_bot
                and is_enabled(event.chat.id, "reactions")
                and _chat_allowed(event.chat.id)
            ):
                now = time.monotonic()
                if _ready(event.chat.id, now):
                    choice = decide(event)
                    if choice and random.randint(1, 100) <= choice[1]:
                        _last[event.chat.id] = now
                        asyncio.create_task(_react(event, choice[0]))
        except Exception as error:
            logger.warning("REACTIONS: %s", error)

        return result
