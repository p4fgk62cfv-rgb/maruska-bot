"""
/срок — сколько человек уже в группе и когда вступил.

    /срок            — про себя
    /срок ответом    — про автора сообщения
    /срок @ник       — про человека по нику

Telegram не сообщает ботам дату вступления, поэтому Мара записывает её
сама, когда видит вход. Кто был в группе раньше Мары — для тех известна
только дата, когда Мара впервые их увидела, и бот честно пишет «как минимум».
"""

from datetime import datetime, timezone
from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from botcontext import display_name_of
from settings.store import local_now, zone


router = Router(name="member_since")


def plural_days(n: int) -> str:
    tail = n % 100
    if 11 <= tail <= 14:
        return "дней"
    return {1: "день", 2: "дня", 3: "дня", 4: "дня"}.get(n % 10, "дней")


def span_text(days: int) -> str:
    """380 → «1 год и 15 дней»; 45 → «45 дней»."""
    if days < 365:
        return f"{days} {plural_days(days)}"
    years, rest = divmod(days, 365)
    year_word = "год" if years % 10 == 1 and years % 100 != 11 else (
        "года" if years % 10 in (2, 3, 4) and years % 100 not in (12, 13, 14) else "лет")
    return f"{years} {year_word}" + (f" и {rest} {plural_days(rest)}" if rest else "")


def format_since(name: str, joined_local: datetime, today, exact: bool, left: bool) -> str:
    days = (today - joined_local.date()).days
    date = joined_local.strftime("%d.%m.%Y")
    who = f"<b>{escape(name)}</b>"

    if left:
        return f"🚪 {who} уже не в группе. Дата вступления была: {date}."

    if not exact and days == 0:
        return f"📅 {who} в группе как минимум с сегодняшнего дня, {date} — раньше Мара этого человека не видела."

    if not exact:
        return (
            f"📅 {who} в группе как минимум с <b>{date}</b> — это уже <b>{span_text(days)}</b>.\n"
            "<i>Точную дату Мара не знает: человек был здесь ещё до того, как она начала следить.</i>"
        )

    if days == 0:
        return f"📅 {who} — новичок: в группе с сегодняшнего дня, {date}. Добро пожаловать! 👋"

    return f"📅 {who} в группе с <b>{date}</b> — уже <b>{span_text(days)}</b>."


@router.message(Command("срок", "since", "staj", ignore_case=True))
async def since_command(message: Message):
    if message.chat.type not in ("group", "supergroup"):
        await message.reply("📅 /срок работает в группе.")
        return

    from database.repository import member_since
    from features.moderation import _target_of

    target = await _target_of(message) or message.from_user
    if target is None:
        return

    info = await member_since(message.chat.id, target.id)

    if info is None:
        await message.reply(f"📅 Мара ещё не видела <b>{escape(display_name_of(target))}</b> в этой группе.")
        return

    joined = info["joined_at"]
    if joined.tzinfo is None:
        joined = joined.replace(tzinfo=timezone.utc)

    name = display_name_of(target) if getattr(target, "first_name", None) else (info["name"] or "Участник")

    await message.reply(format_since(
        name, joined.astimezone(zone(message.chat.id)), local_now(message.chat.id).date(),
        info["exact"], info["left_at"] is not None,
    ))
