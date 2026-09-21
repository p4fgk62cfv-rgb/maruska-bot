"""
Достижения.

Каждое — запись в этом файле. Условие проверяется по словарю
статистики, который собирается из профиля, так что новое
достижение не требует ни миграций, ни новых счётчиков, если
нужный показатель уже считается.

За разблокировку капают алмазы — так достижения не просто
украшение, а повод постараться.
"""

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Achievement:
    key: str
    emoji: str
    title: str
    description: str
    reward: int
    check: Callable[[dict], bool]
    secret: bool = False      # не показывать в списке, пока не открыто


def _at_least(field: str, value: int) -> Callable[[dict], bool]:
    return lambda stats: stats.get(field, 0) >= value


ACHIEVEMENTS: tuple[Achievement, ...] = (
    # Общение
    Achievement(
        "first_words", "👋", "Первое слово",
        "Написать первое сообщение", 20,
        _at_least("messages", 1),
    ),
    Achievement(
        "talker", "💬", "Болтун",
        "Написать 500 сообщений", 150,
        _at_least("messages", 500),
    ),
    Achievement(
        "chatterbox", "📢", "Душа компании",
        "Написать 5000 сообщений", 800,
        _at_least("messages", 5000),
    ),

    # Уровни
    Achievement(
        "level_5", "🍀", "Свой человек",
        "Достичь 5 уровня", 100,
        _at_least("level", 5),
    ),
    Achievement(
        "level_10", "⭐", "Знаток",
        "Достичь 10 уровня", 300,
        _at_least("level", 10),
    ),
    Achievement(
        "level_25", "🔥", "Ветеран",
        "Достичь 25 уровня", 1000,
        _at_least("level", 25),
    ),

    # Бонус и серии
    Achievement(
        "first_bonus", "🎁", "Начало положено",
        "Забрать первый ежедневный бонус", 20,
        _at_least("bonus_days", 1),
    ),
    Achievement(
        "week_streak", "🔥", "Неделя подряд",
        "Серия бонусов 7 дней", 200,
        _at_least("best_streak", 7),
    ),
    Achievement(
        "month_streak", "🌋", "Железная воля",
        "Серия бонусов 30 дней", 1000,
        _at_least("best_streak", 30),
    ),

    # Деньги
    Achievement(
        "first_thousand", "💰", "Первая тысяча",
        "Накопить 1000 алмазов", 100,
        _at_least("coins", 1000),
    ),
    Achievement(
        "rich", "🏦", "Богач",
        "Накопить 10 000 алмазов", 700,
        _at_least("coins", 10000),
    ),

    # Игры
    Achievement(
        "first_win", "🎯", "Угадал!",
        "Первая победа в игре", 30,
        _at_least("games_won", 1),
    ),
    Achievement(
        "sharp_eye", "🧠", "Острый глаз",
        "10 побед в играх", 200,
        _at_least("games_won", 10),
    ),
    Achievement(
        "champion", "🏆", "Чемпион",
        "50 побед в играх", 900,
        _at_least("games_won", 50),
    ),
    Achievement(
        "artist", "🎨", "Художник",
        "Собрать 10 лайков за рисунки", 250,
        _at_least("likes", 10),
    ),

    # Магазин
    Achievement(
        "shopper", "🛍", "Покупатель",
        "Купить первую вещь", 30,
        _at_least("items", 1),
    ),
    Achievement(
        "collector", "🎒", "Коллекционер",
        "Собрать 25 вещей", 400,
        _at_least("items", 25),
    ),
    Achievement(
        "generous", "🎀", "Щедрый",
        "Подарить 10 подарков", 300,
        _at_least("gifts_sent", 10),
    ),

    # Репутация
    Achievement(
        "respected", "⭐", "Уважаемый",
        "Набрать 50 рейтинга", 200,
        _at_least("karma", 50),
    ),

    # Секретное
    Achievement(
        "night_owl", "🦉", "Сова",
        "Забрать бонус между 3 и 5 утра", 150,
        lambda stats: stats.get("night_bonus", False),
        secret=True,
    ),
)


ACHIEVEMENT_BY_KEY = {item.key: item for item in ACHIEVEMENTS}


def check(stats: dict, unlocked: set[str]) -> list[Achievement]:
    """
    Что открылось только что: условие выполнено, а в списке ещё нет.
    """
    return [
        item
        for item in ACHIEVEMENTS
        if item.key not in unlocked and item.check(stats)
    ]


def total_reward(items) -> int:
    return sum(item.reward for item in items)
