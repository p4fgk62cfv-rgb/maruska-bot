"""
Топы группы: кто больше всех написал сообщений и слов.

Telegram считает командой только латиницу без пробелов, поэтому:
  «топ болтунов», «топ сообщений за неделю», «топ слов за месяц» — ловим как текст;
  /chatters, /topmessages месяц, /topwords неделя — латинские команды.

Периоды: за день (сегодня), за неделю (последние 7 дней), за месяц (последние 30).
«Сегодня» — по часовому поясу группы, а не сервера.
"""

import re
from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from settings.store import get_number, is_enabled, local_now


router = Router(name="chatters")

TEXT_RE = re.compile(r"^\s*/?\s*топ\s+болтун(ов|ы)?\s*[!?.]*\s*$", re.IGNORECASE)

MEDALS = ("🥇", "🥈", "🥉")


# ---------------------------------------------------------
# Чистые функции — покрыты тестами
# ---------------------------------------------------------

def is_top_request(text: str | None) -> bool:
    return bool(text) and TEXT_RE.match(text) is not None


RATING_RE = re.compile(
    r"^\s*/?\s*топ\s+(болтун(?:ов|ы)?|сообщений|слов)"
    r"(?:\s+за\s+(день|сегодня|сутки|неделю|месяц))?\s*[!?.]*\s*$",
    re.IGNORECASE,
)

PERIODS = {"day": 1, "week": 7, "month": 30}

PERIOD_WORDS = {
    "день": "day", "сегодня": "day", "сутки": "day", "day": "day", "today": "day",
    "неделю": "week", "неделя": "week", "week": "week",
    "месяц": "month", "month": "month",
}

PERIOD_TITLES = {"day": "за сегодня", "week": "за неделю", "month": "за месяц"}


def parse_rating(text: str | None) -> tuple[str, str] | None:
    """«топ слов за неделю» → ("words", "week"); не запрос топа — None."""
    match = RATING_RE.match(text or "")
    if not match:
        return None
    metric = "words" if match.group(1).lower() == "слов" else "messages"
    return metric, PERIOD_WORDS.get((match.group(2) or "день").lower(), "day")


def period_from_args(args: str | None) -> str:
    """Аргумент команды: «/topwords неделя» → week. Непонятное — за день."""
    return PERIOD_WORDS.get((args or "").strip().lower(), "day")


def plural_words(n: int) -> str:
    tail = n % 100
    if 11 <= tail <= 14:
        return "слов"
    return {1: "слово", 2: "слова", 3: "слова", 4: "слова"}.get(n % 10, "слов")


def format_rating(people: list[dict], total: int, speakers: int, metric: str, period: str, dates: str) -> str:
    plural = plural_words if metric == "words" else plural_messages
    head = "📝 <b>Топ слов" if metric == "words" else "💬 <b>Топ сообщений"

    if not people:
        when = {"day": "Сегодня", "week": "За неделю", "month": "За месяц"}[period]
        return f"{head} {PERIOD_TITLES[period]}</b>\n\n{when} ещё никто ничего не написал. Будь первым!"

    lines = [f"{head} {PERIOD_TITLES[period]}</b> · {dates}\n"]

    for place, person in enumerate(people, start=1):
        mark = MEDALS[place - 1] if place <= len(MEDALS) else f"{place}."
        share = round(person["amount"] * 100 / total) if total else 0
        lines.append(
            f"{mark} <b>{escape(person['name'])}</b> — {person['amount']} "
            f"{plural(person['amount'])}" + (f" · {share}%" if share else "")
        )

    lines.append(f"\nВсего: {total} {plural(total)} от {speakers} чел.")

    if metric == "words" and total and people[0]["amount"] * 2 >= total and len(people) > 1:
        lines.append(f"🎤 {escape(people[0]['name'])} говорит больше, чем все остальные вместе")

    return "\n".join(lines)


def plural_messages(n: int) -> str:
    tail = n % 100
    if 11 <= tail <= 14:
        return "сообщений"
    return {1: "сообщение", 2: "сообщения", 3: "сообщения", 4: "сообщения"}.get(n % 10, "сообщений")


def format_top(people: list[dict], total: int, speakers: int, date_label: str) -> str:
    if not people:
        return "🗣 Сегодня ещё никто не писал. Будь первым!"

    lines = [f"🗣 <b>Топ болтунов за сегодня</b> · {date_label}\n"]
    top = people[0]["messages"] or 1

    for place, person in enumerate(people, start=1):
        mark = MEDALS[place - 1] if place <= len(MEDALS) else f"{place}."
        share = round(person["messages"] * 100 / total) if total else 0
        lines.append(
            f"{mark} <b>{escape(person['name'])}</b> — {person['messages']} "
            f"{plural_messages(person['messages'])}" + (f" · {share}%" if share else "")
        )

    lines.append(f"\nВсего сегодня: {total} {plural_messages(total)} от {speakers} чел.")

    # Лидер сильно впереди — лёгкая подколка
    if len(people) > 1 and people[1]["messages"] and top >= people[1]["messages"] * 2:
        lines.append(f"👑 {escape(people[0]['name'])} сегодня болтает за двоих")

    return "\n".join(lines)


# ---------------------------------------------------------
# Обработчики
# ---------------------------------------------------------

def _wanted(message: Message) -> bool:
    return message.chat.type in ("group", "supergroup") and is_top_request(message.text)


def _rating_wanted(message: Message) -> bool:
    # «топ болтунов» за сегодня отвечает старый обработчик, остальное — здесь
    return (
        message.chat.type in ("group", "supergroup")
        and not is_top_request(message.text)
        and parse_rating(message.text) is not None
    )


async def _answer_rating(message: Message, metric: str, period: str) -> None:
    if message.chat.type not in ("group", "supergroup"):
        await message.reply("📊 Топы работают в группах.")
        return

    if not is_enabled(message.chat.id, "top_chatters"):
        await message.reply("📊 Топы в этой группе выключены (/settings).")
        return

    from datetime import timedelta

    from database.repository import top_period

    today = local_now(message.chat.id).date()
    since = today - timedelta(days=PERIODS[period] - 1)
    size = get_number(message.chat.id, "top_chatters_size") or 10

    data = await top_period(message.chat.id, since.isoformat(), today.isoformat(), metric=metric, limit=size)
    dates = today.strftime("%d.%m") if period == "day" else f"{since.strftime('%d.%m')}–{today.strftime('%d.%m')}"

    await message.answer(format_rating(data["people"], data["total"], data["speakers"], metric, period, dates))


async def _answer(message: Message) -> None:
    if message.chat.type not in ("group", "supergroup"):
        await message.reply("🗣 Топ болтунов работает в группах.")
        return

    if not is_enabled(message.chat.id, "top_chatters"):
        await message.reply("🗣 Топ болтунов в этой группе выключен (/settings).")
        return

    from database.repository import top_chatters

    now = local_now(message.chat.id)
    size = get_number(message.chat.id, "top_chatters_size") or 10

    data = await top_chatters(message.chat.id, now.strftime("%Y-%m-%d"), limit=size)

    await message.answer(format_top(data["people"], data["total"], data["speakers"], now.strftime("%d.%m")))


@router.message(Command("chatters", "talkers"))
async def chatters_command(message: Message):
    await _answer(message)


@router.message(_wanted)
async def chatters_text(message: Message):
    await _answer(message)


@router.message(Command("topwords", "words"))
async def topwords_command(message: Message, command: CommandObject):
    await _answer_rating(message, "words", period_from_args(command.args))


@router.message(Command("topmessages", "topmsg"))
async def topmessages_command(message: Message, command: CommandObject):
    await _answer_rating(message, "messages", period_from_args(command.args))


@router.message(_rating_wanted)
async def rating_text(message: Message):
    metric, period = parse_rating(message.text)
    await _answer_rating(message, metric, period)
