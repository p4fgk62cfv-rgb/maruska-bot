"""
Журнал событий: одна функция на весь бот.

Запись идёт в фоне — журнал не должен тормозить ни ответы бота,
ни кнопки в панели. Если база недоступна, событие теряется, но
ничего не ломается.
"""

import asyncio
import logging

logger = logging.getLogger("maruska.audit")


def log(category: str, action: str, **fields) -> None:
    async def write():
        try:
            from database.repository import add_audit

            await add_audit(category=category, action=action, **fields)
        except Exception as error:
            logger.warning("AUDIT: %s", error)

    try:
        asyncio.get_running_loop().create_task(write())
    except RuntimeError:
        pass


def count(chat_id: int | None, field: str) -> None:
    """Счётчик дневной статистики — тоже в фоне."""
    if chat_id is None or chat_id >= 0:
        return

    async def write():
        try:
            from database.repository import bump_daily_stat

            await bump_daily_stat(chat_id, field)
        except Exception as error:
            logger.warning("STAT %s: %s", field, error)

    try:
        asyncio.get_running_loop().create_task(write())
    except RuntimeError:
        pass


def count_amount(chat_id: int | None, field: str, amount: int) -> None:
    """Как count(), но на произвольную величину — например, выданный опыт."""
    if chat_id is None or chat_id >= 0 or not amount:
        return

    async def write():
        try:
            from database.repository import bump_daily_stat

            await bump_daily_stat(chat_id, field, amount)
        except Exception as error:
            logger.warning("STAT %s: %s", field, error)

    try:
        asyncio.get_running_loop().create_task(write())
    except RuntimeError:
        pass
