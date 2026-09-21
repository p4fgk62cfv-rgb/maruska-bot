"""
Экономика: алмазы 💎

Алмазы приходят только из ежедневного бонуса и игр — за обычные
сообщения ничего не капает, чтобы не поощрять флуд ради заработка.

Все суммы вынесены сюда, чтобы балансировать игру в одном месте.
"""

import os
import random

CURRENCY = "💎"
CURRENCY_NAME = "алмаз"


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw.lstrip("-").isdigit() else default


# Ежедневный бонус — случайная сумма в диапазоне
BONUS_MIN = _int_env("BONUS_MIN", 50)
BONUS_MAX = _int_env("BONUS_MAX", 150)

# Редкий крупный выигрыш, чтобы бонус не приедался
JACKPOT_CHANCE = 0.05
JACKPOT_MIN = _int_env("JACKPOT_MIN", 300)
JACKPOT_MAX = _int_env("JACKPOT_MAX", 500)

# Награды за игры
REWARD_GAME_WIN = _int_env("REWARD_GAME_WIN", 25)
REWARD_GAME_HOST = _int_env("REWARD_GAME_HOST", 15)


REASONS = {
    "bonus": "Ежедневный бонус",
    "jackpot": "Джекпот",
    "game_win": "Победа в игре",
    "game_host": "Ведущий раунда",
    "gift_out": "Подарок отправлен",
    "gift_in": "Подарок получен",
    "purchase": "Покупка",
    "admin": "Начисление вручную",
}


def roll_bonus() -> tuple[int, bool]:
    """
    Возвращает (сумма, это ли джекпот).
    """
    if random.random() < JACKPOT_CHANCE:
        return random.randint(JACKPOT_MIN, JACKPOT_MAX), True

    return random.randint(BONUS_MIN, BONUS_MAX), False


def plural(amount: int) -> str:
    """
    1 алмаз, 2 алмаза, 5 алмазов
    """
    value = abs(amount) % 100

    if 11 <= value <= 14:
        return "алмазов"

    last = value % 10

    if last == 1:
        return "алмаз"
    if last in (2, 3, 4):
        return "алмаза"

    return "алмазов"


def money(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + f" {CURRENCY}"


def reason_text(reason: str, note: str | None = None) -> str:
    return note or REASONS.get(reason, reason)


def wealth_title(balance: int) -> str:
    if balance >= 10000:
        return "Магнат"
    if balance >= 5000:
        return "Богач"
    if balance >= 2000:
        return "При деньгах"
    if balance >= 500:
        return "Копит"
    if balance >= 100:
        return "На карманные"
    return "Пока пусто"


STREAK_FLAMES = ((30, "🔥🔥🔥"), (14, "🔥🔥"), (3, "🔥"))


def streak_mark(streak: int) -> str:
    for threshold, mark in STREAK_FLAMES:
        if streak >= threshold:
            return mark
    return ""
