"""
Приветствие новых участников.

Человека добавили в чат, и он не знает, что бот умеет. Короткое
сообщение с парой команд решает это лучше, чем закреплённый пост,
который никто не читает.
"""

import logging
import random
from html import escape

from aiogram import F, Router
from aiogram.types import ChatMemberUpdated, Message

from database.repository import save_user

from settings.registry import DEFAULT_GREETING, DEFAULT_GREETING_HINT

from settings.store import get_text, is_enabled


logger = logging.getLogger("maruska.greeting")

router = Router(name="greeting")


# Стандартные варианты. Если админ задал свой текст в /settings,
# берётся он, а эти нужны только для разнообразия по умолчанию.
GREETINGS = (
    DEFAULT_GREETING,
    "👋 О, новенький! Привет, <b>{name}</b>.",
    "👋 <b>{name}</b> с нами. Уже интересно.",
    "👋 Привет, <b>{name}</b>! Чувствуй себя как дома.",
    "👋 Встречайте: <b>{name}</b>.",
)


def greeting_line(chat_id: int, name: str) -> str:
    """
    Свой текст группы, а если его нет — случайный стандартный.
    """
    own = get_text(chat_id, "greeting_text")

    template = own if own != DEFAULT_GREETING else random.choice(GREETINGS)

    try:
        return template.format(name=name)
    except (KeyError, IndexError, ValueError):
        # Админ мог вписать что-то непонятное — не падаем
        return template


def greeting_hint(chat_id: int) -> str:
    return get_text(chat_id, "greeting_hint") or DEFAULT_GREETING_HINT


def _name(user) -> str:
    return escape(user.first_name or user.username or "Новенький")


async def welcome(bot, chat_id: int, users) -> None:
    people = [user for user in users if user and not user.is_bot]

    if not people:
        return

    if len(people) == 1:
        head = greeting_line(chat_id, _name(people[0]))
    else:
        names = ", ".join(f"<b>{_name(user)}</b>" for user in people)
        head = f"👋 Пополнение: {names}"

    for user in people:
        try:
            await save_user(
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name,
            )
        except Exception as error:
            logger.warning("GREET SAVE: %s", error)

    try:
        await bot.send_message(
            chat_id,
            f"{head}\n\n{greeting_hint(chat_id)}",
        )
    except Exception as error:
        logger.warning("GREET SEND: %s %s", type(error).__name__, error)


@router.message(F.new_chat_members)
async def new_members(message: Message):
    """
    Классическое служебное сообщение о добавлении участника.
    """
    if not is_enabled(message.chat.id, "greeting"):
        return

    me = await message.bot.me()

    # Если добавили самого бота — здороваемся с чатом, а не с собой
    added_self = any(
        user.id == me.id for user in (message.new_chat_members or [])
    )

    if added_self:
        await message.answer(
            "👋 Всем привет! Я Мара.\n\n"
            + greeting_hint(message.chat.id)
            + "\n\n⚙️ <code>/settings</code> — что включить, "
            "а что выключить (для админов)"
        )
        return

    await welcome(message.bot, message.chat.id, message.new_chat_members)


@router.chat_member()
async def member_joined(event: ChatMemberUpdated):
    """
    Современный способ: Telegram присылает это событие, даже когда
    человек зашёл сам по ссылке-приглашению.
    """
    if not is_enabled(event.chat.id, "greeting"):
        return

    was = event.old_chat_member.status
    now = event.new_chat_member.status

    joined = was in ("left", "kicked") and now in ("member", "administrator")

    if not joined:
        return

    await welcome(event.bot, event.chat.id, [event.new_chat_member.user])
