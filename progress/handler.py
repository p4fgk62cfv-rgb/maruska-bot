"""
Команды прогресса: /level, /achievements, /toplevel
"""

import logging
from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database.repository import (
    collect_stats,
    get_profile,
    get_unlocked_achievements,
    get_xp_top,
    save_user,
)

from progress.achievements import ACHIEVEMENTS
from progress.service import profile_block
from progress.xp import level_title

from settings.store import is_enabled


logger = logging.getLogger("maruska.progress")

router = Router(name="progress")


def progress_on(message: Message) -> bool:
    return is_enabled(message.chat.id, "progress")


def display_name(user) -> str:
    return user.first_name or user.username or "Игрок"


@router.message(Command("level", "xp"))
async def level_command(message: Message):
    if not progress_on(message):
        await message.reply("🎚 Уровни в этой группе выключены (/settings).")
        return

    user = message.from_user

    if user is None:
        return

    await save_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    profile = await get_profile(user.id)
    xp = profile.xp if profile else 0

    stats = await collect_stats(user.id)
    unlocked = await get_unlocked_achievements(user.id)

    await message.reply(
        f"👤 <b>{escape(display_name(user))}</b>\n\n"
        + profile_block(xp)
        + f"\n💬 Сообщений: <b>{stats.get('messages', 0)}</b>\n"
        + f"🏅 Достижений: <b>{len(unlocked)}</b> из {len(ACHIEVEMENTS)}\n\n"
        + "/achievements — список"
    )


@router.message(Command("achievements", "ach"))
async def achievements_command(message: Message):
    if not progress_on(message):
        await message.reply("🏅 Достижения в этой группе выключены (/settings).")
        return

    user = message.from_user

    if user is None:
        return

    unlocked = await get_unlocked_achievements(user.id)

    done = []
    todo = []

    for item in ACHIEVEMENTS:
        if item.key in unlocked:
            done.append(f"{item.emoji} <b>{item.title}</b> — {item.description}")
        elif not item.secret:
            todo.append(f"🔒 {item.title} — {item.description}")

    secret_left = sum(
        1
        for item in ACHIEVEMENTS
        if item.secret and item.key not in unlocked
    )

    lines = [
        f"🏅 <b>Достижения</b> — {len(unlocked)} из {len(ACHIEVEMENTS)}\n"
    ]

    if done:
        lines.append("<b>Открыто</b>")
        lines.extend(done)

    if todo:
        lines.append("\n<b>Осталось</b>")
        lines.extend(todo[:12])

        if len(todo) > 12:
            lines.append(f"…и ещё {len(todo) - 12}")

    if secret_left:
        lines.append(f"\n❔ Секретных: {secret_left}")

    await message.reply("\n".join(lines))


@router.message(Command("toplevel", "topxp"))
async def top_level_command(message: Message):
    if not progress_on(message):
        await message.reply("🎚 Уровни в этой группе выключены (/settings).")
        return

    users = await get_xp_top(limit=10)

    if not users:
        await message.reply("🎚 Пока никто не набрал опыта.")
        return

    lines = ["🎚 <b>Топ по уровню</b>\n"]
    medals = ["🥇", "🥈", "🥉"]

    for index, profile in enumerate(users, start=1):
        medal = medals[index - 1] if index <= 3 else f"{index}."
        name = escape(profile.display_name or "Игрок")

        lines.append(
            f"{medal} <b>{name}</b> — {level_title(profile.level or 1)} "
            f"(ур. {profile.level or 1}, {profile.xp} xp)"
        )

    await message.reply("\n".join(lines))
