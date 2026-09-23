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

from database.repository import (
    bump_daily_stat,
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

        return await handler(event, data)



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
        if (
            isinstance(event, Message)
            and event.chat.id < 0
            and event.from_user is not None
            and not event.from_user.is_bot
        ):
            # В фоне: запись в базу не должна тормозить ответ
            asyncio.create_task(_count(event.chat.id))

        return await handler(event, data)


async def _count(chat_id: int) -> None:
    try:
        await bump_daily_stat(chat_id, "messages")
    except Exception as error:
        logger.warning("STATS: %s", error)
