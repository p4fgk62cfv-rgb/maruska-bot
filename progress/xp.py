"""
Опыт и уровни.

Опыт — не то же самое, что алмазы. Алмазы копятся редко и тратятся,
опыт копится постоянно и не тратится никогда: он показывает, сколько
человек прожил в чате.

Поэтому опыт капает и за обычные сообщения — но с потолком в сутки,
чтобы флудом уровень не выбивался.
"""

import os


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw.lstrip("-").isdigit() else default


# Сколько опыта за что
XP_MESSAGE = _int_env("XP_MESSAGE", 2)
XP_DAILY_CAP = _int_env("XP_DAILY_CAP", 120)      # потолок за сообщения в сутки
XP_BONUS = _int_env("XP_BONUS", 30)
XP_GAME_WIN = _int_env("XP_GAME_WIN", 60)
XP_GAME_HOST = _int_env("XP_GAME_HOST", 40)
XP_LIKE = _int_env("XP_LIKE", 5)
XP_GIFT = _int_env("XP_GIFT", 15)


# Порог уровня растёт квадратично: 1-й — 100, 2-й — 300, 3-й — 600…
LEVEL_STEP = _int_env("LEVEL_STEP", 100)


LEVEL_TITLES = (
    (50, "🏛 Легенда чата"),
    (40, "👑 Император"),
    (30, "💎 Магистр"),
    (25, "🔥 Ветеран"),
    (20, "⚔️ Мастер"),
    (15, "🎖 Бывалый"),
    (10, "⭐ Знаток"),
    (7, "🌟 Активист"),
    (5, "🍀 Свой человек"),
    (3, "🌱 Освоился"),
    (1, "👋 Новичок"),
)


def xp_for_level(level: int) -> int:
    """
    Сколько всего опыта нужно, чтобы достичь уровня.
    Уровень 1 — 0 опыта, дальше по нарастающей.
    """
    if level <= 1:
        return 0

    n = level - 1

    return LEVEL_STEP * n * (n + 1) // 2


def level_from_xp(xp: int) -> int:
    level = 1

    while xp >= xp_for_level(level + 1):
        level += 1

        if level > 200:      # страховка от бесконечного цикла
            break

    return level


def level_title(level: int) -> str:
    for threshold, title in LEVEL_TITLES:
        if level >= threshold:
            return title

    return LEVEL_TITLES[-1][1]


def progress(xp: int) -> dict:
    """
    Всё, что нужно показать в профиле.
    """
    level = level_from_xp(xp)

    current_floor = xp_for_level(level)
    next_floor = xp_for_level(level + 1)

    span = max(next_floor - current_floor, 1)
    done = xp - current_floor

    return {
        "level": level,
        "title": level_title(level),
        "xp": xp,
        "into_level": done,
        "need": span,
        "left": max(next_floor - xp, 0),
        "percent": min(int(done * 100 / span), 100),
    }


def bar(percent: int, width: int = 10) -> str:
    filled = max(0, min(width, round(percent * width / 100)))
    return "█" * filled + "░" * (width - filled)
