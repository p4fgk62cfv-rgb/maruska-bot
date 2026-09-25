"""
Автоответы: на ключевое слово — заготовленная фраза.

У каждого правила: слово-триггер, способ совпадения (содержит /
точно / начинается с), вероятность срабатывания и пауза между
срабатываниями. Проверка в памяти, без базы.

Стоит после действий и перед разговором с Марой: если сработал
автоответ, Gemini не тратится.
"""

import logging
import random
import re
import time
from dataclasses import dataclass

from aiogram import Router
from aiogram.types import Message

from botcontext import display_name_of

from settings.store import is_blocked, is_enabled


logger = logging.getLogger("maruska.autoreplies")

router = Router(name="autoreplies")

MATCHES = ("contains", "exact", "start")
MAX_TRIGGER = 100
MAX_RESPONSE = 1000


@dataclass
class Rule:
    id: int
    trigger: str
    response: str
    match: str = "contains"
    probability: int = 100
    cooldown: int = 30
    enabled: bool = True


_rules: dict[int, list[Rule]] = {}
_last_fired: dict[tuple[int, int], float] = {}
_pending: dict[tuple[int, int], Rule] = {}


# ---------------------------------------------------------
# Чистые функции — покрыты тестами
# ---------------------------------------------------------

def normalize(text: str) -> str:
    cleaned = (text or "").lower().replace("ё", "е")
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return " ".join(cleaned.split())


def matches(rule: Rule, text: str) -> bool:
    needle = normalize(rule.trigger)
    haystack = normalize(text)

    if not needle or not haystack:
        return False

    if rule.match == "exact":
        return haystack == needle

    if rule.match == "start":
        return haystack == needle or haystack.startswith(needle + " ")

    # «содержит» — целым словом или фразой, а не куском слова:
    # триггер «кот» не должен срабатывать на «который»
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack) is not None


def validate(trigger: str, response: str, match: str, probability, cooldown) -> str | None:
    if len(normalize(trigger)) < 2:
        return "Слово-триггер слишком короткое"

    if len(trigger) > MAX_TRIGGER:
        return f"Триггер длиннее {MAX_TRIGGER} символов"

    if not (response or "").strip():
        return "Нужен текст ответа"

    if len(response) > MAX_RESPONSE:
        return f"Ответ длиннее {MAX_RESPONSE} символов"

    if match not in MATCHES:
        return "Неизвестный способ совпадения"

    try:
        if not 1 <= int(probability) <= 100:
            return "Вероятность — от 1 до 100%"
        if not 0 <= int(cooldown) <= 86400:
            return "Пауза — от 0 до 86400 секунд"
    except (TypeError, ValueError):
        return "Вероятность и пауза — числа"

    return None


def render(response: str, name: str) -> str:
    return response.replace("{name}", name)


# ---------------------------------------------------------
# Кэш группы
# ---------------------------------------------------------

def prime(chat_id: int, rows) -> None:
    _rules[chat_id] = [
        Rule(
            id=row.id, trigger=row.trigger, response=row.response,
            match=row.match or "contains", probability=row.probability or 100,
            cooldown=row.cooldown or 0, enabled=bool(row.enabled),
        )
        for row in rows
    ]


def is_loaded(chat_id: int) -> bool:
    return chat_id in _rules


async def reload(chat_id: int) -> None:
    from database.repository import list_autoreplies

    prime(chat_id, await list_autoreplies(chat_id))


def find(chat_id: int, text: str, now: float | None = None, roll: float | None = None) -> Rule | None:
    """Первое подходящее правило, которое не на паузе и выпало по вероятности."""
    now = time.monotonic() if now is None else now

    for rule in _rules.get(chat_id, []):
        if not rule.enabled or not matches(rule, text):
            continue

        last = _last_fired.get((chat_id, rule.id))

        if last is not None and now - last < rule.cooldown:
            continue

        chance = random.random() if roll is None else roll

        if chance * 100 >= rule.probability:
            continue

        return rule

    return None


# ---------------------------------------------------------
# Обработчик
# ---------------------------------------------------------

def is_autoreply(message: Message) -> bool:
    if message.chat.type not in ("group", "supergroup"):
        return False

    if not message.text or message.text.startswith("/"):
        return False

    if message.from_user is None or message.from_user.is_bot:
        return False

    if not is_enabled(message.chat.id, "autoreplies"):
        return False

    if is_blocked(message.chat.id, message.from_user.id):
        return False

    rule = find(message.chat.id, message.text)

    if rule is None:
        return False

    _pending[(message.chat.id, message.message_id)] = rule

    if len(_pending) > 500:
        _pending.clear()

    return True


@router.message(is_autoreply)
async def autoreply(message: Message):
    rule = _pending.pop((message.chat.id, message.message_id), None)

    if rule is None:
        return

    # Сообщение сюда перехвачено до разговора с Марой — поэтому
    # учитываем его здесь же: счётчики, опыт, память
    import asyncio

    import context_cache
    from features.chat import persist_message, remembers

    name = display_name_of(message.from_user)
    keep = remembers(message)

    if keep:
        context_cache.remember(message.chat.id, name, message.text)

    asyncio.create_task(persist_message(message, name, keep))

    _last_fired[(message.chat.id, rule.id)] = time.monotonic()

    try:
        await message.reply(render(rule.response, display_name_of(message.from_user)), parse_mode=None)
    except Exception as error:
        logger.warning("AUTOREPLY: %s", error)
        return

    import audit

    audit.count(message.chat.id, "autoreplies")

    try:
        from database.repository import bump_autoreply

        await bump_autoreply(rule.id)
    except Exception:
        pass
