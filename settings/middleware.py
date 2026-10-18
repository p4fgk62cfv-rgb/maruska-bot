"""
Прогрев настроек до фильтров.

Внешняя мидлварь выполняется раньше, чем фильтры хендлеров,
поэтому к моменту проверки is_enabled() значения уже в памяти.
"""

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

import asyncio
import re

from database.repository import (
    list_action_custom,
    bump_daily_stat,
    bump_hourly,
    disabled_actions,
    get_blocked_ids,
    get_group_settings,
)

from settings import store


logger = logging.getLogger("maruska.settings")


class SettingsMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable[Any]],
        event: TelegramObject,
        data: dict,
    ) -> Any:
        chat = None

        if isinstance(event, Message):
            chat = event.chat
        elif isinstance(event, CallbackQuery) and event.message:
            chat = event.message.chat

        if chat is not None and chat.id < 0 and not store.is_loaded(chat.id):
            try:
                values = await get_group_settings(chat.id)
            except Exception as error:
                logger.warning("SETTINGS LOAD: %s", error)
                values = {}

            store.prime(chat.id, values)

            try:
                store.prime_blocked(chat.id, await get_blocked_ids(chat.id))
            except Exception as error:
                logger.warning("BLOCKED LOAD: %s", error)
                store.prime_blocked(chat.id, set())

            try:
                store.prime_actions(chat.id, await disabled_actions(chat.id))
            except Exception as error:
                logger.warning("ACTIONS LOAD: %s", error)
                store.prime_actions(chat.id, set())

            try:
                from features import automod as _automod

                await _automod.reload_rules(chat.id)
            except Exception as error:
                logger.warning("PUNISH RULES LOAD: %s", error)

            try:
                from features import autoreplies

                await autoreplies.reload(chat.id)
            except Exception as error:
                logger.warning("AUTOREPLIES LOAD: %s", error)

            try:
                from economy import shop_rules

                await shop_rules.reload(chat.id)
            except Exception as error:
                logger.warning("SHOP RULES LOAD: %s", error)

            try:
                from actions import custom as action_custom

                action_custom.prime(chat.id, await list_action_custom(chat.id))
            except Exception as error:
                logger.warning("ACTION CUSTOM LOAD: %s", error)

        # Отключённые в группе команды: у обычных участников молча
        # не срабатывают, у админов работают как раньше
        if isinstance(event, Message) and await command_blocked(event):
            return None

        return await handler(event, data)


def command_name(text: str | None) -> str | None:
    """«/dice@BotMaruska_bot 2d6» → «dice»."""
    if not text or not text.startswith("/"):
        return None

    return text[1:].split(maxsplit=1)[0].split("@", 1)[0].lower() or None


def parse_commands(raw: str) -> set[str]:
    import re as _re

    return {
        item.strip().lstrip("/").lower()
        for item in _re.split(r"[,\s;]+", raw or "")
        if item.strip().lstrip("/")
    }


async def command_blocked(message: Message) -> bool:
    chat = message.chat

    if chat.type not in ("group", "supergroup") or message.from_user is None:
        return False

    name = command_name(message.text)

    if name is None:
        return False

    # /settings и /help не отключаются — иначе админка станет недоступна
    if name in ("settings", "help", "start"):
        return False

    if name not in parse_commands(store.get_text(chat.id, "disabled_commands")):
        return False

    from features.automod import _is_admin

    return not await _is_admin(message.bot, chat.id, message.from_user.id)



class StatsMiddleware(BaseMiddleware):
    """
    Считает каждое сообщение группы для графиков панели.

    Стоит снаружи, до роутеров: раньше счётчик жил в последнем
    обработчике, и всё, что перехватили раньше — действия, команды,
    отгадки в крокодиле — в статистику не попадало.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable[Any]],
        event: TelegramObject,
        data: dict,
    ) -> Any:
        if isinstance(event, Message) and event.chat.id < 0 and event.chat.title:
            _check_title(event.chat.id, event.chat.title)

        if (
            isinstance(event, Message)
            and event.chat.id < 0
            and event.from_user is not None
            and not event.from_user.is_bot
            and not is_service(event)
        ):
            # В фоне: запись в базу не должна тормозить ответ
            asyncio.create_task(_count(event.chat.id))

            asyncio.create_task(_bump_user(event.chat.id, event.from_user.id, count_words(event.text or event.caption)))

            if _first_today(event.chat.id, event.from_user.id):
                asyncio.create_task(_bump(event.chat.id, "active_users"))

            if event.text and event.text.startswith("/"):
                asyncio.create_task(_bump(event.chat.id, "commands"))

        return await handler(event, data)


# Служебные события — «вошёл», «закрепил», «сменил название» — не сообщения:
# в топ болтунов и графики их не считаем
SERVICE_TYPES = frozenset({
    "new_chat_members", "left_chat_member", "new_chat_title", "new_chat_photo",
    "delete_chat_photo", "group_chat_created", "supergroup_chat_created",
    "migrate_to_chat_id", "migrate_from_chat_id", "pinned_message",
    "message_auto_delete_timer_changed", "video_chat_scheduled", "video_chat_started",
    "video_chat_ended", "video_chat_participants_invited", "forum_topic_created",
    "forum_topic_edited", "forum_topic_closed", "forum_topic_reopened",
    "general_forum_topic_hidden", "general_forum_topic_unhidden", "boost_added",
    "chat_background_set", "write_access_allowed", "users_shared", "chat_shared",
    "proximity_alert_triggered",
})


def is_service(message: Message) -> bool:
    kind = getattr(message, "content_type", None)
    # ContentType — перечисление: str() дал бы «ContentType.NEW_CHAT_MEMBERS»
    return getattr(kind, "value", kind) in SERVICE_TYPES


# Название группы, которое уже видели: группу переименовали — обновляем панель
_titles: dict[int, str] = {}


def _check_title(chat_id: int, title: str) -> None:
    if _titles.get(chat_id) == title:
        return
    _titles[chat_id] = title
    asyncio.create_task(_save_title(chat_id, title))


async def _save_title(chat_id: int, title: str) -> None:
    try:
        from database.repository import remember_chat
        from webapp.admin import drop_all_access

        if await remember_chat(chat_id, title):
            logger.info("CHAT TITLE: группа %s теперь «%s»", chat_id, title)
            drop_all_access()
    except Exception as error:
        _titles.pop(chat_id, None)
        logger.warning("CHAT TITLE: %s", error)


# Кто уже писал сегодня — чтобы считать активных, а не сообщения.
# После перезапуска бота в тот же день человек может быть учтён
# повторно; для графика это погрешность в пределах одного дня.
_seen_today: dict[int, tuple[str, set[int]]] = {}


def _first_today(chat_id: int, user_id: int) -> bool:
    import time as _time

    day = _time.strftime("%Y-%m-%d", _time.gmtime())
    stored_day, users = _seen_today.get(chat_id, ("", set()))

    if stored_day != day:
        users = set()

    if user_id in users:
        return False

    users.add(user_id)
    _seen_today[chat_id] = (day, users)

    return True


_WORD_RE = re.compile(r"[^\W_]+(?:[-'’][^\W_]+)*")


def count_words(text: str | None) -> int:
    """Слова в сообщении: «Привет, как дела?» — 3. Ссылки и @ники — тоже по словам, эмодзи — нет."""
    return len(_WORD_RE.findall(text or ""))


async def _bump_user(chat_id: int, user_id: int, words: int = 0) -> None:
    """Сообщения и слова человека за сегодня — для топов. День — местный."""
    try:
        from database.repository import bump_user_daily

        await bump_user_daily(chat_id, store.local_now(chat_id).strftime("%Y-%m-%d"), user_id, words)
    except Exception as error:
        logger.warning("STATS USER: %s", error)


async def _bump(chat_id: int, field: str) -> None:
    try:
        await bump_daily_stat(chat_id, field)
    except Exception as error:
        logger.warning("STATS %s: %s", field, error)


async def _count(chat_id: int) -> None:
    try:
        await bump_daily_stat(chat_id, "messages")
        await bump_hourly(chat_id)
    except Exception as error:
        logger.warning("STATS: %s", error)
