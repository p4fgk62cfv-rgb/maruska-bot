"""
Связка опыта, достижений и наград.

Одна точка входа: award() начисляет опыт, проверяет достижения,
выдаёт за них алмазы и возвращает, о чём стоит сообщить в чат.
Так любое новое событие подключается одной строкой.
"""

import logging
from html import escape

from database.repository import (
    award_xp,
    change_balance,
    collect_stats,
    get_unlocked_achievements,
    unlock_achievement,
)

from economy.service import CURRENCY, plural
from progress.achievements import check
from progress.xp import bar, level_title, progress


logger = logging.getLogger("maruska.progress")


async def award(
    telegram_id: int,
    amount: int,
    display_name: str | None = None,
    chat_id: int | None = None,
    daily_cap: int | None = None,
    per_message: bool = False,
    with_economy: bool = True,
    extra_stats: dict | None = None,
) -> dict:
    """
    Начислить опыт и проверить достижения.

    Возвращает {level_up, level, unlocked, reward} — всё, что нужно
    показать человеку. Пустой результат означает «молчи».
    """
    result = await award_xp(
        telegram_id=telegram_id,
        amount=amount,
        display_name=display_name,
        daily_cap=daily_cap,
        per_message=1 if per_message else 0,
    )

    unlocked = []
    reward = 0

    try:
        stats = await collect_stats(telegram_id)

        if extra_stats:
            stats.update(extra_stats)

        already = await get_unlocked_achievements(telegram_id)
        fresh = check(stats, already)

        for item in fresh:
            if not await unlock_achievement(telegram_id, item.key):
                continue

            unlocked.append(item)
            reward += item.reward

        if reward and with_economy:
            await change_balance(
                telegram_id=telegram_id,
                amount=reward,
                reason="achievement",
                note="Достижения",
                chat_id=chat_id,
                display_name=display_name,
            )

    except Exception as error:
        logger.warning("ACHIEVEMENTS: %s %s", type(error).__name__, error)

    return {
        "level_up": result.get("level_up", False),
        "level": result.get("level", 1),
        "xp": result.get("xp", 0),
        "gained": result.get("gained", 0),
        "unlocked": unlocked,
        "reward": reward if with_economy else 0,
    }


def level_up_text(name: str, level: int) -> str:
    return (
        f"🎉 <b>{escape(name)}</b> берёт <b>{level} уровень</b>!\n"
        f"{level_title(level)}"
    )


def unlocked_text(name: str, items, reward: int, with_economy: bool) -> str:
    if not items:
        return ""

    head = (
        f"🏅 <b>{escape(name)}</b> открывает достижение:"
        if len(items) == 1
        else f"🏅 <b>{escape(name)}</b> открывает достижения:"
    )

    lines = [head, ""]

    for item in items:
        lines.append(f"{item.emoji} <b>{item.title}</b> — {item.description}")

    if reward and with_economy:
        lines.append(f"\n{CURRENCY} Награда: <b>{reward} {plural(reward)}</b>")

    return "\n".join(lines)


def profile_block(xp: int) -> str:
    data = progress(xp)

    return (
        f"🎚 Уровень <b>{data['level']}</b> — {data['title']}\n"
        f"<code>{bar(data['percent'])}</code> {data['percent']}%\n"
        f"✨ Опыт: <b>{data['xp']}</b>, до следующего {data['left']}\n"
    )
