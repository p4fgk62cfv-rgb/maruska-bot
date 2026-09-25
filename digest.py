"""
Недельные итоги.

Раз в неделю бот подводит итог: кто был активнее всех, кто больше
заработал, кто чаще выигрывал. Это работает на всю группу сразу и
держит людей лучше, чем персональный ежедневный бонус.

Рассылка идёт только по живым чатам — тем, где на этой неделе
кто-то писал.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from botcontext import display_name_of

from database.repository import (
    get_active_chats,
    get_member,
    get_week_earners,
    get_week_top,
    get_week_winners,
)

from economy.service import money

from settings.store import get_number, is_enabled, is_loaded, prime
from database.repository import get_group_settings


logger = logging.getLogger("maruska.digest")

router = Router(name="digest")


# Когда подводим итоги: день недели (0 — понедельник) и час UTC
DIGEST_WEEKDAY = int(os.getenv("DIGEST_WEEKDAY", "6") or 6)   # воскресенье
DIGEST_HOUR = int(os.getenv("DIGEST_HOUR", "17") or 17)

CHECK_INTERVAL = 600      # как часто просыпаться, секунды

MEDALS = ("🥇", "🥈", "🥉", "4.", "5.")


def _plural_days(days: int) -> str:
    value = days % 100

    if 11 <= value <= 14:
        return "дней"

    last = value % 10

    if last == 1:
        return "день"
    if last in (2, 3, 4):
        return "дня"

    return "дней"


async def build_digest(chat_id: int) -> str | None:
    """
    Текст итогов или None, если за неделю ничего не происходило.
    """
    top = await get_week_top(chat_id, limit=5)

    if not top:
        return None

    total = sum(member.week_messages for member in top)

    if total < 10:
        # Слишком тихая неделя, нечего подводить
        return None

    lines = ["📊 <b>Итоги недели</b>\n", "<b>Самые разговорчивые</b>"]

    for index, member in enumerate(top):
        medal = MEDALS[index] if index < len(MEDALS) else f"{index + 1}."
        name = escape(member.display_name or "Участник")
        lines.append(f"{medal} <b>{name}</b> — {member.week_messages}")

    earners = await get_week_earners(chat_id, limit=3)

    if earners:
        lines.append("\n<b>Больше всех заработали</b>")
        for index, (name, amount) in enumerate(earners):
            lines.append(
                f"{MEDALS[index]} <b>{escape(name)}</b> — {money(amount)}"
            )

    winners = await get_week_winners(chat_id, limit=3)

    if winners:
        lines.append("\n<b>Победы в играх</b>")
        for index, (name, wins) in enumerate(winners):
            lines.append(f"{MEDALS[index]} <b>{escape(name)}</b> — {wins}")

    lines.append("\n<i>Новая неделя — новые счётчики.</i>")

    return "\n".join(lines)


@router.message(Command("digest", "week"))
async def digest_command(message: Message):
    if not is_enabled(message.chat.id, "digest"):
        await message.reply("📊 Итоги в этой группе выключены (/settings).")
        return

    text = await build_digest(message.chat.id)

    if text is None:
        await message.reply(
            "📊 На этой неделе ещё слишком тихо, подводить нечего."
        )
        return

    await message.answer(text)


@router.message(Command("mydays", "days"))
async def days_command(message: Message):
    """
    Сколько человек уже в этом чате.
    """
    if message.from_user is None or message.chat.type == "private":
        return

    member = await get_member(message.chat.id, message.from_user.id)

    if member is None:
        await message.reply("Я тебя тут ещё не запомнила. Напиши что-нибудь!")
        return

    days = max((datetime.utcnow() - member.joined_at).days, 0)
    name = escape(display_name_of(message.from_user))

    if days == 0:
        phrase = "сегодня первый день"
    else:
        phrase = f"уже <b>{days}</b> {_plural_days(days)}"

    await message.reply(
        f"📅 <b>{name}</b> здесь {phrase}.\n"
        f"💬 Сообщений за всё время: <b>{member.messages_count}</b>\n"
        f"📈 За эту неделю: <b>{member.week_messages}</b>"
    )


# ---------------------------------------------------------
# Еженедельная рассылка
# ---------------------------------------------------------

_sent_weeks: dict[int, str] = {}


def _week_key(moment: datetime) -> str:
    year, week, _ = moment.isocalendar()
    return f"{year}-W{week:02d}"


async def digest_loop(bot):
    """
    Фоновая задача: раз в десять минут проверяет, не пора ли
    подвести итоги, и рассылает их по живым чатам.
    """
    logger.info(
        "Итоги недели: по умолчанию %s, %s:00 UTC (у групп может быть своё)",
        ("пн", "вт", "ср", "чт", "пт", "сб", "вс")[DIGEST_WEEKDAY % 7],
        DIGEST_HOUR,
    )

    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL)

            now = datetime.now(timezone.utc)

            week = _week_key(now)
            chats = await get_active_chats()

            for chat_id in chats:
                if _sent_weeks.get(chat_id) == week:
                    continue

                # Настройки чата могли ещё не попасть в кэш
                if not is_loaded(chat_id):
                    try:
                        prime(chat_id, await get_group_settings(chat_id))
                    except Exception:
                        prime(chat_id, {})

                if not is_enabled(chat_id, "digest"):
                    continue

                # День и час у каждой группы свои
                weekday = get_number(chat_id, "digest_weekday")
                hour = get_number(chat_id, "digest_hour")

                if weekday is None:
                    weekday = DIGEST_WEEKDAY

                if hour is None:
                    hour = DIGEST_HOUR

                # День и час — по часовому поясу группы, а не сервера
                from settings.store import local_now

                here = local_now(chat_id)

                if here.weekday() != weekday or here.hour != hour:
                    continue

                text = await build_digest(chat_id)

                _sent_weeks[chat_id] = week

                if text is None:
                    continue

                try:
                    await bot.send_message(chat_id, text)
                    await asyncio.sleep(0.5)      # не частим с отправкой
                except Exception as error:
                    logger.warning(
                        "DIGEST SEND %s: %s", chat_id, error
                    )

        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.error("DIGEST LOOP: %s %s", type(error).__name__, error)
