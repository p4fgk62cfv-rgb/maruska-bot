"""
Прогрев настроек до фильтров.

Внешняя мидлварь выполняется раньше, чем фильтры хендлеров,
поэтому к моменту проверки is_enabled() значения уже в памяти.
"""

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from database.repository import get_group_settings

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

        return await handler(event, data)
