"""
Команды экономики: баланс, ежедневный бонус, история, топ богачей.
"""

import logging
import re
from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database.repository import (
    claim_daily_bonus,
    get_balance,
    get_profile,
    get_richest,
    get_transactions,
    save_user,
)

from economy.service import (
    CURRENCY,
    money,
    plural,
    reason_text,
    roll_bonus,
    streak_mark,
    wealth_title,
)

from settings.store import is_enabled


logger = logging.getLogger("maruska.economy")

router = Router(name="economy")

BONUS_RE = re.compile(r"\b(бонус\w*|ежедневн\w+)\b", re.IGNORECASE)
BALANCE_RE = re.compile(r"\b(баланс\w*|алмаз\w*|сколько у меня)\b", re.IGNORECASE)

MAX_TRIGGER_WORDS = 4

_WORDS_RE = re.compile(r"[А-Яа-яЁёA-Za-z]+")


def display_name(user) -> str:
    return user.first_name or user.username or "Игрок"


def economy_on(message: Message) -> bool:
    return is_enabled(message.chat.id, "economy")


def _short(message: Message, pattern: re.Pattern) -> bool:
    """
    Триггер засчитывается только короткой фразой, чтобы бот
    не влезал в разговор со словом «баланс».
    """
    if not message.text or message.text.startswith("/"):
        return False

    if message.from_user is None or message.from_user.is_bot:
        return False

    if not economy_on(message):
        return False

    if not pattern.search(message.text):
        return False

    return len(_WORDS_RE.findall(message.text)) <= MAX_TRIGGER_WORDS


# ---------------------------------------------------------
# Баланс
# ---------------------------------------------------------

async def send_balance(message: Message):
    user = message.from_user

    if user is None or user.is_bot:
        return

    await save_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    balance = await get_balance(user.id)
    profile = await get_profile(user.id)

    streak = profile.bonus_streak if profile else 0
    best = profile.best_streak if profile else 0

    lines = [
        f"{CURRENCY} <b>{escape(display_name(user))}</b>",
        "",
        f"Баланс: <b>{money(balance)}</b>",
        f"Статус: <b>{wealth_title(balance)}</b>",
    ]

    if streak:
        mark = streak_mark(streak)
        lines.append(f"Серия бонусов: <b>{streak}</b> {mark}".rstrip())

    if best > streak:
        lines.append(f"Лучшая серия: <b>{best}</b>")

    lines.append("\n/bonus — забрать ежедневный")

    await message.reply("\n".join(lines))


@router.message(Command("balance", "diamonds"))
async def balance_command(message: Message):
    if not economy_on(message):
        await message.reply(f"{CURRENCY} Экономика в этой группе выключена (/settings).")
        return

    await send_balance(message)


@router.message(lambda m: _short(m, BALANCE_RE))
async def balance_text(message: Message):
    await send_balance(message)


# ---------------------------------------------------------
# Ежедневный бонус
# ---------------------------------------------------------

async def send_bonus(message: Message):
    user = message.from_user

    if user is None or user.is_bot:
        return

    await save_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    amount, jackpot = roll_bonus()

    try:
        result = await claim_daily_bonus(
            telegram_id=user.id,
            amount=amount,
            chat_id=message.chat.id,
            display_name=display_name(user),
        )
    except Exception as error:
        logger.error("BONUS: %s %s", type(error).__name__, error)
        await message.reply("Не получилось выдать бонус, попробуй позже 😔")
        return

    if not result["claimed"]:
        await message.reply(
            f"{CURRENCY} Сегодня бонус уже забран.\n"
            f"Баланс: <b>{money(result['balance'])}</b>\n"
            f"Серия: <b>{result['streak']}</b> {streak_mark(result['streak'])}\n\n"
            "Приходи завтра."
        )
        return

    streak = result["streak"]
    mark = streak_mark(streak)

    head = (
        f"🎰 <b>ДЖЕКПОТ!</b>\n\n"
        if jackpot
        else f"{CURRENCY} <b>Ежедневный бонус</b>\n\n"
    )

    await message.reply(
        head
        + f"Тебе выпало <b>{amount} {plural(amount)}</b>\n"
        + f"Баланс: <b>{money(result['balance'])}</b>\n"
        + f"🔥 Серия: <b>{streak}</b> {mark}".rstrip()
    )


@router.message(Command("bonus", "daily"))
async def bonus_command(message: Message):
    if not economy_on(message):
        await message.reply(f"{CURRENCY} Экономика в этой группе выключена (/settings).")
        return

    await send_bonus(message)


@router.message(lambda m: _short(m, BONUS_RE))
async def bonus_text(message: Message):
    await send_bonus(message)


# ---------------------------------------------------------
# История
# ---------------------------------------------------------

@router.message(Command("history"))
async def history_command(message: Message):
    if not economy_on(message):
        await message.reply(f"{CURRENCY} Экономика в этой группе выключена (/settings).")
        return

    if message.from_user is None:
        return

    items = await get_transactions(message.from_user.id, limit=10)

    if not items:
        await message.reply(
            f"{CURRENCY} Операций пока нет.\n/bonus — начать копить."
        )
        return

    lines = [f"{CURRENCY} <b>Последние операции</b>\n"]

    for item in items:
        sign = "+" if item.amount > 0 else ""
        date = item.created_at.strftime("%d.%m")
        lines.append(
            f"<code>{date}</code>  <b>{sign}{item.amount}</b>  "
            f"{escape(reason_text(item.reason, item.note))}"
        )

    balance = await get_balance(message.from_user.id)
    lines.append(f"\nСейчас: <b>{money(balance)}</b>")

    await message.reply("\n".join(lines))


# ---------------------------------------------------------
# Топ богачей
# ---------------------------------------------------------

@router.message(Command("rich", "topcoins"))
async def rich_command(message: Message):
    if not economy_on(message):
        await message.reply(f"{CURRENCY} Экономика в этой группе выключена (/settings).")
        return

    users = await get_richest(limit=10)

    if not users:
        await message.reply(f"{CURRENCY} Пока никто ничего не накопил.")
        return

    lines = [f"{CURRENCY} <b>Самые богатые</b>\n"]
    medals = ["🥇", "🥈", "🥉"]

    for index, profile in enumerate(users, start=1):
        medal = medals[index - 1] if index <= 3 else f"{index}."
        name = escape(profile.display_name or "Игрок")
        lines.append(f"{medal} <b>{name}</b> — {money(profile.coins)}")

    await message.reply("\n".join(lines))
