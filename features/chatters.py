"""
Топ болтунов за сегодня.

Telegram считает командой только латиницу без пробелов, поэтому:
  «топ болтунов» / «/топ болтунов» — ловим как текст;
  /chatters — латинская команда для меню бота в BotFather.

«Сегодня» — по часовому поясу группы, а не сервера.
"""

import re
from html import escape

from aiogram import Router
from aiogram.filters import Command
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
