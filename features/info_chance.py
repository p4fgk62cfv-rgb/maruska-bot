"""
«Мара, инфа …» — Мара называет вероятность случайным процентом.

    Мара, инфа что Стас сегодня чокнулся
    → 🔮 Вероятность инфы: <b>Что Стас сегодня чокнулся</b>
      Составляет <b>73%</b>

Нужно обращение к Маре и слово «инфа» в начале. Процент каждый раз новый.
"""

import random
import re
from html import escape

from aiogram import Router
from aiogram.types import Message

from botcontext import TRIGGER_RE, is_addressed
from settings.store import is_enabled


router = Router(name="info_chance")

MAX_LENGTH = 200

_INFO = re.compile(r"^[\s,.!:—-]*инф(?:а|у|ы)(?![а-яё])(?:\s*[,:—-])?\s*(.*)$", re.IGNORECASE | re.DOTALL)

# Короткая приписка к проценту — по уровню
VERDICTS = (
    (0, ("Фейк чистой воды 🙅", "Даже не мечтай 😂", "Враньё на 100% 🤥")),
    (11, ("Очень вряд ли 🤨", "Сомнительно, но окэй 🤷", "Звёзды фыркают 🙄")),
    (31, ("Ну такое… 🤔", "Может быть, а может и нет 🎲", "Пятьдесят на пятьдесят, почти 🪙")),
    (51, ("Похоже на правду 👀", "Что-то в этом есть 🧐", "Маруська склоняется к «да» 😏")),
    (71, ("Почти наверняка 🔥", "Факты не врут 📈", "Я бы поставила на это 💸")),
    (91, ("Стопроцентная инфа! 💯", "Это даже не слух, это факт 📜", "Подтверждено Маруськой ✅")),
)


def parse(text: str | None) -> str | None:
    """«Мара, инфа что Стас сегодня чокнулся» → «Что Стас сегодня чокнулся». Не то — None."""
    if not text or text.startswith("/"):
        return None
    found = TRIGGER_RE.search(text)
    if found is None:
        return None
    body = text[found.end():]
    match = _INFO.match(body)
    if match is None:
        return None
    statement = " ".join(match.group(1).split()).rstrip("?!. ")
    if not statement:
        return ""
    return (statement[0].upper() + statement[1:])[:MAX_LENGTH]


def verdict(percent: int) -> str:
    options = VERDICTS[0][1]
    for floor, texts in VERDICTS:
        if percent >= floor:
            options = texts
    return random.choice(options)


def answer(statement: str, percent: int) -> str:
    return (
        f"🔮 Вероятность инфы: <b>{escape(statement)}</b>\n"
        f"Составляет <b>{percent}%</b>\n\n{verdict(percent)}"
    )


def is_info_question(message: Message) -> bool:
    if message.from_user is None or message.from_user.is_bot:
        return False
    if message.chat.type in ("group", "supergroup") and not is_enabled(message.chat.id, "info_chance"):
        return False
    return parse(message.text) is not None and is_addressed(message)


@router.message(is_info_question)
async def info_chance(message: Message):
    statement = parse(message.text)
    if not statement:
        await message.reply("🔮 Какую инфу проверить? Например: <b>Мара, инфа что Стас сегодня чокнулся</b>")
        return
    await message.reply(answer(statement, random.randint(0, 100)))
