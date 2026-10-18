"""
Расход нейросетей: сколько ответов дала каждая модель за день,
сколько раз упёрлась в лимит и сколько токенов ушло.

Пишется в базу в фоне (таблица ai_usage), чтобы перезапуски бота
не сбрасывали счёт. День — московский: так его видит владелец.
"""

import asyncio
import logging


logger = logging.getLogger("maruska.ai")

DAY_ZONE = "Europe/Moscow"

OUTCOMES = ("ok", "limit", "error")


def today() -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo(DAY_ZONE)).strftime("%Y-%m-%d")


def is_limit(status_or_error) -> bool:
    text = str(status_or_error).lower()
    return text == "429" or any(m in text for m in ("429", "resource_exhausted", "quota", "rate limit", "too many requests"))


def record(provider: str, model: str, outcome: str, tokens: int = 0) -> None:
    """Отметить один запрос к нейросети. Никогда не мешает ответу."""
    if outcome not in OUTCOMES:
        outcome = "error"

    async def write():
        try:
            from database.repository import bump_ai_usage

            await bump_ai_usage(today(), provider, model or "?", outcome, max(0, int(tokens or 0)))
        except Exception as error:
            logger.warning("AI USAGE: %s %s", type(error).__name__, error)

    try:
        asyncio.get_running_loop().create_task(write())
    except RuntimeError:
        pass
