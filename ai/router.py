"""
Кто отвечает за Маруську: Gemini, а если она не может — запасная нейросеть.

Переключение незаметно для чата. Если Gemini упёрлась в лимит, следующие
GEMINI_PAUSE_MINUTES (по умолчанию 15) минут её даже не спрашиваем —
иначе каждый ответ ждал бы отказа Google. Потом пробуем снова.
"""

import logging
import os
import time

from ai import fallback


logger = logging.getLogger("maruska.ai")

PAUSE = float(os.getenv("GEMINI_PAUSE_MINUTES", "15")) * 60

_paused_until = 0.0

# Для панели и логов: кто отвечал и сколько раз
stats = {"gemini": 0, "fallback": 0, "last": "", "last_error": ""}


def is_quota(error: Exception) -> bool:
    text = f"{type(error).__name__} {error}".lower()
    return any(mark in text for mark in ("429", "resource_exhausted", "quota", "rate limit", "ratelimit", "too many requests"))


def gemini_paused() -> bool:
    return time.monotonic() < _paused_until


async def ask_ai(prompt: str, persona: str | None = None, use_search: bool = False) -> str:
    """Ответ Маруськи. Исключение — только если не ответил никто."""
    global _paused_until

    from ai import gemini

    error: Exception | None = None

    if not gemini_paused():
        try:
            answer, _sources = await gemini.ask_gemini(prompt, use_search=use_search, persona=persona)
            if answer:
                stats["gemini"] += 1
                stats["last"] = "Gemini"
                return answer
        except Exception as caught:
            error = caught
            stats["last_error"] = f"{type(caught).__name__}: {str(caught)[:200]}"
            if is_quota(caught):
                _paused_until = time.monotonic() + PAUSE
                logger.warning("AI: у Gemini кончился лимит — %d мин отвечает запасная нейросеть", PAUSE // 60)
            else:
                logger.warning("AI: Gemini не ответила (%s) — отвечает запасная нейросеть", type(caught).__name__)

    if not fallback.configured():
        if error is not None:
            raise error
        # Gemini на паузе или промолчала, а запасной нет — молчим и мы
        return ""

    from ai.prompts import build_prompt

    try:
        answer, who = await fallback.ask_fallback(
            build_prompt(persona), prompt,
            temperature=gemini.TEMPERATURE, max_tokens=gemini.MAX_OUTPUT_TOKENS,
        )
    except Exception as fallback_error:
        logger.error("AI FALLBACK: никто не ответил — %s", fallback_error)
        raise error or fallback_error

    stats["fallback"] += 1
    stats["last"] = who
    return answer
