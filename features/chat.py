"""
Разговор с Марой.

Здесь же живёт «болтливость» — настройка того, насколько охотно
она вмешивается. Мара, которая отвечает на каждое обращение и
никогда не молчит, в живом чате быстро надоедает.
"""

import asyncio
import re
import logging
import random
import time

from aiogram import Router
from aiogram.types import Message

import context_cache

from ai.gemini import ask_gemini

from botcontext import display_name_of, is_addressed

from database.repository import (
    get_recent_messages,
    save_message,
    save_user,
)

from progress.service import award, level_up_text, unlocked_text
from progress.xp import XP_DAILY_CAP, XP_MESSAGE

from settings.store import get_number, get_text, get_value, is_blocked, is_enabled


logger = logging.getLogger("maruska.chat")

router = Router(name="chat")

CONTEXT_MESSAGES = 8


# ---------------------------------------------------------
# Болтливость
# ---------------------------------------------------------
#
# quiet  — отвечает по имени, но не чаще раза в пару минут
# normal — отвечает всегда, когда обращаются
# active — плюс изредка вмешивается сама
#
# ---------------------------------------------------------

QUIET_COOLDOWN = 120        # секунд между ответами в тихом режиме
ACTIVE_CHANCE = 0.06        # шанс вмешаться без обращения
FUN_CHANCE = 0.15           # развлекательный режим вмешивается чаще

FUN_HINT = (
    "Сейчас режим развлечения: будь игривее, шути больше, "
    "подкалывай по-доброму, предлагай мини-игры и челленджи.\n\n"
)

_last_reply: dict[int, float] = {}

# Лимиты AI: сколько ответов за сутки и когда отвечали человеку
_daily: dict[int, tuple[str, int]] = {}
_user_last: dict[tuple[int, int], float] = {}


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def within_limits(chat_id: int, user_id: int | None) -> bool:
    """Суточный лимит группы и пауза для одного человека."""
    limit = get_number(chat_id, "ai_daily_limit") or 0

    if limit:
        day, used = _daily.get(chat_id, ("", 0))
        if day == _today() and used >= limit:
            return False

    pause = get_number(chat_id, "ai_cooldown") or 0

    if pause and user_id is not None:
        last = _user_last.get((chat_id, user_id))
        if last is not None and time.monotonic() - last < pause:
            return False

    return True


def note_reply(chat_id: int, user_id: int | None) -> None:
    day, used = _daily.get(chat_id, ("", 0))
    _daily[chat_id] = (_today(), used + 1 if day == _today() else 1)

    if user_id is not None:
        _user_last[(chat_id, user_id)] = time.monotonic()


def parse_exceptions(raw: str) -> set[str]:
    """«@kate, 12345, Vasya» → {"kate", "12345", "vasya"}."""
    return {
        item.strip().lstrip("@").lower()
        for item in re.split(r"[,\s;]+", raw or "")
        if item.strip().lstrip("@")
    }


def remembers(message: Message) -> bool:
    """Запоминать ли это сообщение: память включена и человек не в исключениях."""
    chat_id = message.chat.id

    if not is_enabled(chat_id, "memory"):
        return False

    user = message.from_user

    if user is None:
        return True

    excluded = parse_exceptions(get_text(chat_id, "memory_except"))

    if not excluded:
        return True

    return not (
        str(user.id) in excluded
        or (user.username or "").lower() in excluded
    )


def set_context_size(size: int) -> None:
    global CONTEXT_MESSAGES

    CONTEXT_MESSAGES = max(1, size)


def should_answer(message: Message) -> bool:
    if not is_enabled(message.chat.id, "ai"):
        return False

    if is_blocked(message.chat.id, message.from_user.id if message.from_user else None):
        return False

    mode = get_value(message.chat.id, "chattiness") or "normal"

    if not within_limits(message.chat.id, message.from_user.id if message.from_user else None):
        return False

    addressed = is_addressed(message)

    if addressed:
        if mode != "quiet":
            return True

        # Тихий режим: не частим
        last = _last_reply.get(message.chat.id, 0)

        if time.monotonic() - last < QUIET_COOLDOWN:
            return False

        return True

    # Без обращения вмешиваемся только в активном и развлекательном режимах
    if mode not in ("active", "fun"):
        return False

    if message.chat.type == "private":
        return False

    if not message.text or len(message.text) < (8 if mode == "fun" else 12):
        return False

    return random.random() < (FUN_CHANCE if mode == "fun" else ACTIVE_CHANCE)


@router.message(lambda message: message.text is not None)
async def ai_handler(message: Message):
    if not message.from_user or message.from_user.is_bot:
        return

    # Неизвестные команды в Gemini не отправляем.
    if message.text.startswith("/"):
        return

    name = display_name_of(message.from_user)

    # Контекст держим в памяти: чтение из базы перед каждым
    # ответом добавляло заметную задержку.
    keep = remembers(message)

    if keep:
        context_cache.remember(message.chat.id, name, message.text)

    # Запись в базу не задерживает ответ — уходит в фон.
    asyncio.create_task(persist_message(message, name, keep))

    if not should_answer(message):
        return

    _last_reply[message.chat.id] = time.monotonic()
    note_reply(message.chat.id, message.from_user.id if message.from_user else None)

    import audit

    audit.count(message.chat.id, "ai_requests")

    if message.from_user and message.chat.id < 0:

        from database.repository import bump_member_counter

        async def _count_ai(chat_id=message.chat.id, user_id=message.from_user.id):
            try:
                await bump_member_counter(chat_id, user_id, "ai_count")
            except Exception:
                pass

        asyncio.create_task(_count_ai())

    # Показываем "печатает..." сразу, чтобы ожидание не было немым.
    try:
        await message.bot.send_chat_action(message.chat.id, "typing")
    except Exception:
        pass

    if not context_cache.is_loaded(message.chat.id):
        try:
            history = await get_recent_messages(
                message.chat.id,
                limit=get_number(message.chat.id, "context_messages")
                or CONTEXT_MESSAGES,
            )
            context_cache.prime(message.chat.id, history)
        except Exception as error:
            logger.warning("CONTEXT LOAD: %s", error)
            context_cache.prime(message.chat.id, [])

    depth = get_number(message.chat.id, "context_messages") or CONTEXT_MESSAGES

    # Память выключена — Мара видит только само обращение
    recent_messages = (
        context_cache.recent(message.chat.id, depth)
        if is_enabled(message.chat.id, "memory") else []
    )

    fun = (get_value(message.chat.id, "chattiness") or "normal") == "fun"

    from i18n import ai_instruction

    prompt = (
        ai_instruction(message.chat.id)
        + (FUN_HINT if fun else "")
        + ("Последние сообщения группы:\n" + "\n".join(recent_messages) + "\n\n" if recent_messages else "")
        + "Новое сообщение пользователя:\n"
        + message.text
    )

    try:
        answer, _sources = await ask_gemini(
            prompt,
            use_search=False,
            persona=get_value(message.chat.id, "persona"),
        )
    except Exception as error:
        logger.error("GEMINI ERROR: %s %s", type(error).__name__, error)
        await message.reply("Что-то я задумалась 🤔")
        return

    if not answer:
        return

    context_cache.remember(message.chat.id, "Мара", answer)

    # Ответ модели — обычный текст, HTML-разметку из него не парсим.
    await message.reply(answer, parse_mode=None)


async def persist_message(message: Message, name: str, keep: bool = True):
    """
    Сохранение пользователя и сообщения в базу, вне критического пути.
    Здесь же капает опыт за активность.
    """
    try:
        await save_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )

        await save_message(
            chat_id=message.chat.id,
            telegram_user_id=message.from_user.id,
            username=name,
            message=message.text,
            store_text=keep,
        )
    except Exception as error:
        logger.warning("PERSIST: %s %s", type(error).__name__, error)
        return

    if not is_enabled(message.chat.id, "progress"):
        return

    try:
        result = await award(
            telegram_id=message.from_user.id,
            amount=get_number(message.chat.id, "xp_message") or XP_MESSAGE,
            display_name=name,
            chat_id=message.chat.id,
            daily_cap=(
                get_number(message.chat.id, "xp_daily_cap") or XP_DAILY_CAP
            ),
            per_message=True,
            with_economy=is_enabled(message.chat.id, "economy"),
        )

        await announce_progress(message, name, result)
    except Exception as error:
        logger.warning("XP: %s %s", type(error).__name__, error)


async def announce_progress(message: Message, name: str, result: dict):
    """
    Сообщает о новом уровне и открытых достижениях.
    Молчит, если ничего не произошло.
    """
    if not result:
        return

    parts = []

    if result.get("level_up"):
        parts.append(level_up_text(name, result["level"]))

    if result.get("unlocked"):
        parts.append(
            unlocked_text(
                name,
                result["unlocked"],
                result.get("reward", 0),
                is_enabled(message.chat.id, "economy"),
            )
        )

    if not parts:
        return

    try:
        await message.answer("\n\n".join(parts))
    except Exception as error:
        logger.warning("ANNOUNCE: %s %s", type(error).__name__, error)
