"""
Логика кубиков без Telegram: разбор формата броска и сами броски.

Вынесено отдельно, чтобы тесты могли это проверять, не поднимая
aiogram и не притворяясь ботом.
"""

import random
import re


DICE_RE = re.compile(
    r"^\s*(\d{0,2})\s*[dкд]\s*(\d{1,3})\s*([+-]\s*\d{1,3})?\s*$",
    re.IGNORECASE,
)

MAX_DICE = 20
MAX_SIDES = 1000

FACES = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}

EIGHT_BALL = (
    "Бесспорно", "Предрешено", "Никаких сомнений", "Определённо да",
    "Можешь быть уверен", "Мне кажется — да", "Вероятнее всего",
    "Хорошие перспективы", "Знаки говорят — да", "Да",
    "Пока не ясно, попробуй снова", "Спроси позже",
    "Лучше не рассказывать", "Сейчас нельзя предсказать",
    "Сконцентрируйся и спроси опять",
    "Даже не думай", "Мой ответ — нет", "По моим данным — нет",
    "Перспективы не очень", "Весьма сомнительно",
)


def parse_roll(text: str) -> tuple[int, int, int] | None:
    """
    "2d6+3" -> (2, 6, 3). Понимает и кириллические «к», «д».
    """
    match = DICE_RE.match(text or "")

    if not match:
        return None

    count = int(match.group(1) or 1)
    sides = int(match.group(2))
    modifier = int((match.group(3) or "0").replace(" ", ""))

    if count < 1 or count > MAX_DICE:
        return None

    if sides < 2 or sides > MAX_SIDES:
        return None

    return count, sides, modifier


def roll(count: int, sides: int) -> list[int]:
    return [random.randint(1, sides) for _ in range(count)]
