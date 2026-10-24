"""
Дни рождения.

Мара иногда — в случайный момент, когда человек пишет в группе, —
спрашивает его дату рождения кнопками: месяц, потом день. Каждого
спрашивает один раз; «Не скажу» — больше не пристаёт.

Сказать самому:  «мой др 15.03», /др 15.03, /birthday 15.03
Узнать чужой:    /др ответом на сообщение или /др @ник
Список группы:   «дни рождения», /birthdays
Стереть:         /др удалить

В час, заданный в настройках группы, Мара напоминает: за 2 дня,
накануне — и поздравляет в сам день, с подарком алмазами (раз в год).
Дата хранится одна на человека (день и месяц, без года).
"""

import asyncio
import logging
import random
import re
import time
from datetime import date, timedelta
from html import escape
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
)

from botcontext import display_name_of
from database.database import utcnow
from settings.store import get_number, is_enabled, local_now


logger = logging.getLogger("maruska.birthdays")

router = Router(name="birthdays")

MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря")
MONTHS_SHORT = ("Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек")
MONTH_TITLES = ("Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь")
DAYS_IN_MONTH = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

ASK_CHANCE = 0.12           # шанс спросить подходящего человека при сообщении
ASK_AGAIN_DAYS = 30         # промолчал на вопрос — спросим снова не раньше
CHECK_INTERVAL = 300        # как часто проверять, не пора ли поздравлять

LIST_RE = re.compile(r"^\s*/?\s*(дни\s+рождени[яй]|др\s+группы|у\s+кого\s+(скоро\s+)?(др|день\s+рождения))\s*[!?.]*\s*$", re.IGNORECASE)
MINE_RE = re.compile(r"^\s*(мой\s+(др|день\s+рождения)|у\s+меня\s+(др|день\s+рождения))\s*:?\s*(.+)$", re.IGNORECASE)

ASK_PHRASES = (
    "🎂 {name}, слушай, а когда у тебя день рождения? Хочу поздравить вовремя 😊",
    "🎈 {name}, а у тебя когда день рождения? Мара записывает в календарик 📅",
    "🥳 {name}, раскрой секрет: когда твой день рождения? Обещаю не забыть!",
    "🎁 {name}, Мара собирает дни рождения чата. Твой когда?",
)

CONGRATS = (
    "Пусть всё получается, а настроение будет как в пятницу вечером ✨",
    "Желаем счастья, тепла и чтобы мемы всегда были смешные 😄",
    "Пусть этот год будет самым ярким, а чат — самым уютным 💜",
    "Здоровья, удачи и побольше поводов улыбаться 🥰",
    "Пусть сбудется всё, что загадаешь над тортом 🎂",
    "Пусть деньги водятся, а проблемы не находятся 💸",
)


# ---------------------------------------------------------
# Чистые функции — покрыты тестами
# ---------------------------------------------------------

def valid(day: int, month: int) -> bool:
    return 1 <= month <= 12 and 1 <= day <= DAYS_IN_MONTH[month - 1]


def parse_date(text: str | None) -> tuple[int, int] | None:
    """«15.03», «15/3», «15 марта», «15 мар» → (15, 3); год, если есть, игнорируем."""
    text = (text or "").strip().lower()

    match = re.match(r"^(\d{1,2})[./\-\s](\d{1,2})(?:[./\-\s]\d{2,4})?\s*$", text)
    if match:
        day, month = int(match.group(1)), int(match.group(2))
        return (day, month) if valid(day, month) else None

    match = re.match(r"^(\d{1,2})\s+([а-яё]+)(?:\s+\d{2,4})?\s*$", text)
    if match:
        day, word = int(match.group(1)), match.group(2)
        for index, name in enumerate(MONTHS):
            if word[:3] == name[:3]:
                return (day, index + 1) if valid(day, index + 1) else None

    return None


def human_date(day: int, month: int) -> str:
    return f"{day} {MONTHS[month - 1]}"


def occurrence(day: int, month: int, year: int) -> date:
    """День рождения в этом году. 29 февраля в невисокосный — 28-го."""
    if month == 2 and day == 29:
        try:
            return date(year, 2, 29)
        except ValueError:
            return date(year, 2, 28)
    return date(year, month, day)


def days_until(day: int, month: int, today: date) -> int:
    this_year = occurrence(day, month, today.year)
    if this_year < today:
        this_year = occurrence(day, month, today.year + 1)
    return (this_year - today).days


def plural_days(n: int) -> str:
    tail = n % 100
    if 11 <= tail <= 14:
        return "дней"
    return {1: "день", 2: "дня", 3: "дня", 4: "дня"}.get(n % 10, "дней")


def when_text(days: int) -> str:
    return {0: "сегодня 🎉", 1: "завтра", 2: "послезавтра"}.get(days, f"через {days} {plural_days(days)}")


def format_list(people: list[dict], today: date, limit: int = 20) -> str:
    if not people:
        return ("🎂 В этой группе ещё никто не сказал свой день рождения.\n"
                "Напиши <code>мой др 15.03</code> — Мара запомнит и поздравит!")

    rows = sorted(people, key=lambda p: days_until(p["day"], p["month"], today))[:limit]
    lines = ["🎂 <b>Ближайшие дни рождения</b>\n"]
    for person in rows:
        left = days_until(person["day"], person["month"], today)
        mark = " 🎉" if left == 0 else ""
        tail = f" — {when_text(left)}" if left <= 30 and left else ""
        lines.append(f"• {person['day']:02d}.{person['month']:02d} — <b>{escape(person['name'])}</b>{tail}{mark}")
    return "\n".join(lines)


def reminder_text(kind: str, mention: str, gift: int) -> str:
    if kind == "d2":
        return f"🎈 Послезавтра день рождения у {mention}! Есть время придумать подарок 🎁"
    if kind == "d1":
        return f"⏰ Завтра у {mention} день рождения! Готовим поздравления 🥳"
    if kind == "d3":
        return f"📅 Через 3 дня день рождения у {mention}. Мара напоминает заранее 😉"
    if kind == "d4":
        return f"🗓 Через 4 дня день рождения у {mention}. Самое время подумать о сюрпризе 🤫"
    if kind == "d5":
        return f"🔔 Через 5 дней день рождения у {mention}! Записываем в календарь 📌"
    text = f"🎂 Сегодня день рождения у {mention}! 🎉\nПоздравляем всем чатом! "
    if gift:
        text += f"Мара дарит {gift} 💎 и желает: "
    return text + random.choice(CONGRATS)


MAX_REMIND_DAYS = 5


def due_kinds(days_left: int, remind_days: int) -> list[str]:
    """Что пора отправить: напоминание за N дней (если N ≤ настройки) или поздравление."""
    if days_left == 0:
        return ["d0"]
    if 1 <= days_left <= min(remind_days, MAX_REMIND_DAYS):
        return [f"d{days_left}"]
    return []


# ---------------------------------------------------------
# Кнопки
# ---------------------------------------------------------

def months_keyboard(user_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=MONTHS_SHORT[m], callback_data=f"bd:m:{user_id}:{m + 1}") for m in range(r, r + 4)]
        for r in (0, 4, 8)
    ]
    rows.append([InlineKeyboardButton(text="🙈 Не скажу", callback_data=f"bd:no:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def days_keyboard(user_id: int, month: int) -> InlineKeyboardMarkup:
    days = list(range(1, DAYS_IN_MONTH[month - 1] + 1))
    rows = [
        [InlineKeyboardButton(text=str(d), callback_data=f"bd:d:{user_id}:{month}:{d}") for d in days[i:i + 7]]
        for i in range(0, len(days), 7)
    ]
    rows.append([InlineKeyboardButton(text="← Месяц", callback_data=f"bd:back:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _mention(user_id: int, name: str) -> str:
    return f'<a href="tg://user?id={user_id}">{escape(name)}</a>'


# ---------------------------------------------------------
# Вопрос в случайный момент
# ---------------------------------------------------------

_last_ask: dict[int, float] = {}       # чат → когда спрашивали
_checked: dict[int, float] = {}        # человек → когда проверяли базу (чтобы не дёргать её на каждое сообщение)


async def _maybe_ask(message: Message) -> None:
    chat_id, user = message.chat.id, message.from_user
    now = time.monotonic()

    if now - _last_ask.get(chat_id, -1e9) < (get_number(chat_id, "birthday_ask_hours") or 6) * 3600:
        return
    if random.random() > ASK_CHANCE:
        return
    if now - _checked.get(user.id, -1e9) < 3600:
        return
    _checked[user.id] = now

    from database.repository import birthday_ask_state, get_birthday, mark_birthday_asked

    if await get_birthday(user.id):
        return
    state = await birthday_ask_state(user.id)
    if state and (state["declined"] or utcnow() - state["asked_at"] < timedelta(days=ASK_AGAIN_DAYS)):
        return

    _last_ask[chat_id] = now
    await mark_birthday_asked(user.id)
    await message.reply(
        random.choice(ASK_PHRASES).format(name=f"<b>{escape(display_name_of(user))}</b>"),
        reply_markup=months_keyboard(user.id),
    )


def _access_allowed(chat_id: int, module: str) -> bool:
    from settings import access

    return access.allowed(chat_id, module)


class BirthdayAskMiddleware(BaseMiddleware):
    """После обычной обработки сообщения иногда спрашивает дату рождения."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable[Any]],
        event: TelegramObject,
        data: dict,
    ) -> Any:
        result = await handler(event, data)

        if (
            isinstance(event, Message)
            and event.chat.type in ("group", "supergroup")
            and event.from_user is not None
            and not event.from_user.is_bot
            and event.text
            and not event.text.startswith("/")
            and is_enabled(event.chat.id, "birthdays")
            and _access_allowed(event.chat.id, "social")
        ):
            try:
                await _maybe_ask(event)
            except Exception as error:
                logger.warning("BIRTHDAY ASK: %s %s", type(error).__name__, error)

        return result


# ---------------------------------------------------------
# Кнопки: месяц → день
# ---------------------------------------------------------

async def _owner_only(callback: CallbackQuery, user_id: int) -> bool:
    if callback.from_user.id != user_id:
        await callback.answer("Это вопрос не тебе 😉 Свой день рождения: «мой др 15.03»", show_alert=True)
        return False
    return True


@router.callback_query(F.data.startswith("bd:"))
async def birthday_buttons(callback: CallbackQuery):
    parts = callback.data.split(":")
    kind, user_id = parts[1], int(parts[2])

    if not await _owner_only(callback, user_id):
        return

    from database.repository import mark_birthday_asked, set_birthday

    name = f"<b>{escape(display_name_of(callback.from_user))}</b>"

    if kind == "no":
        await mark_birthday_asked(user_id, declined=True)
        await callback.message.edit_text(f"🙈 Хорошо, {name}, не буду спрашивать. Если передумаешь — «мой др 15.03»")
        await callback.answer()
        return

    if kind == "back":
        await callback.message.edit_reply_markup(reply_markup=months_keyboard(user_id))
        await callback.answer()
        return

    if kind == "m":
        month = int(parts[3])
        await callback.message.edit_text(f"📅 {name}, {MONTH_TITLES[month - 1]} — выбери день:",
                                         reply_markup=days_keyboard(user_id, month))
        await callback.answer()
        return

    if kind == "d":
        month, day = int(parts[3]), int(parts[4])
        if not valid(day, month):
            await callback.answer("Такой даты нет 🤔", show_alert=True)
            return
        await set_birthday(user_id, day, month)
        if callback.message:
            await _remember_member(callback.message.chat, callback.from_user)
        await callback.message.edit_text(
            f"🎂 Запомнила: у {name} день рождения <b>{human_date(day, month)}</b>! Обязательно поздравлю 🥳"
        )
        await callback.answer("Сохранено 🎉")


# ---------------------------------------------------------
# Команды
# ---------------------------------------------------------

async def _remember_member(chat, user) -> None:
    """Сказал дату в группе — значит, он участник: иначе не попадёт в список и поздравления."""
    if chat.type in ("group", "supergroup"):
        from database.repository import ensure_member

        await ensure_member(chat.id, user.id, user.first_name or user.username)


async def _save_text_date(message: Message, raw: str) -> None:
    from database.repository import set_birthday

    parsed = parse_date(raw)
    if parsed is None:
        await message.reply("🤔 Не поняла дату. Напиши так: <code>мой др 15.03</code> или <code>мой др 15 марта</code>")
        return
    await set_birthday(message.from_user.id, *parsed)
    await _remember_member(message.chat, message.from_user)
    await message.reply(f"🎂 Запомнила: <b>{human_date(*parsed)}</b>! Поздравлю обязательно 🥳")


@router.message(Command("др", "birthday", "bday", ignore_case=True))
async def birthday_command(message: Message, command: CommandObject):
    if not message.from_user:
        return

    from database.repository import delete_birthday, get_birthday

    args = (command.args or "").strip()

    if args.lower() in ("удалить", "стереть", "delete", "remove"):
        removed = await delete_birthday(message.from_user.id)
        await message.reply("🗑 Стёрла твой день рождения." if removed else "У меня и не было твоей даты 🙂")
        return

    if args and not args.startswith("@"):
        await _save_text_date(message, args)
        return

    from features.moderation import _target_of

    target = await _target_of(message)

    if target is None or target.id == message.from_user.id:
        saved = await get_birthday(message.from_user.id)
        if saved:
            left = days_until(*saved, local_now(message.chat.id).date())
            await message.reply(f"🎂 Твой день рождения — <b>{human_date(*saved)}</b> ({when_text(left)}).\n"
                                "Поменять: <code>/др 15.03</code> · стереть: <code>/др удалить</code>")
        else:
            await message.reply("🎂 Когда у тебя день рождения?", reply_markup=months_keyboard(message.from_user.id))
        return

    saved = await get_birthday(target.id)
    who = f"<b>{escape(display_name_of(target))}</b>"
    if saved:
        left = days_until(*saved, local_now(message.chat.id).date())
        await message.reply(f"🎂 У {who} день рождения <b>{human_date(*saved)}</b> — {when_text(left)}")
    else:
        await message.reply(f"🤷‍♀️ {who} ещё не говорил(а) Маре свой день рождения.")


@router.message(lambda m: m.text is not None and MINE_RE.match(m.text) is not None)
async def birthday_mine_text(message: Message):
    if not message.from_user or message.from_user.is_bot:
        return
    await _save_text_date(message, MINE_RE.match(message.text).group(4))


@router.message(Command("birthdays"))
async def birthdays_list_command(message: Message):
    await _list(message)


@router.message(lambda m: m.chat.type in ("group", "supergroup") and m.text is not None and LIST_RE.match(m.text) is not None)
async def birthdays_list_text(message: Message):
    await _list(message)


async def _list(message: Message) -> None:
    if message.chat.type not in ("group", "supergroup"):
        await message.reply("🎂 Список дней рождения — в группе.")
        return
    if not is_enabled(message.chat.id, "birthdays"):
        await message.reply("🎂 Дни рождения в этой группе выключены (/settings).")
        return

    from database.repository import chat_birthdays

    await message.answer(format_list(await chat_birthdays(message.chat.id), local_now(message.chat.id).date()))


# ---------------------------------------------------------
# Напоминания и поздравления
# ---------------------------------------------------------

async def run_reminders(bot, chat_id: int) -> int:
    """Одна проверка группы: шлёт то, что пора и ещё не отправлено. Возвращает число сообщений."""
    from database.repository import change_balance, chat_birthdays, mark_birthday_sent

    if not is_enabled(chat_id, "birthdays"):
        return 0

    here = local_now(chat_id)
    if here.hour < (get_number(chat_id, "birthday_hour") if get_number(chat_id, "birthday_hour") is not None else 10):
        return 0

    today = here.date()
    remind = get_number(chat_id, "birthday_remind_days")
    remind = 2 if remind is None else remind
    gift = get_number(chat_id, "birthday_gift") or 0
    if not is_enabled(chat_id, "economy"):
        gift = 0

    sent = 0

    for person in await chat_birthdays(chat_id):
        left = days_until(person["day"], person["month"], today)
        for kind in due_kinds(left, remind):
            # Год самого дня рождения: напоминание 30.12 о дне 01.01 — это уже следующий год
            year = (today + timedelta(days=left)).year
            if not await mark_birthday_sent(chat_id, person["telegram_id"], year, kind):
                continue

            given = 0
            # Подарок — один раз в год на человека, в первой группе, где поздравили
            if kind == "d0" and gift and await mark_birthday_sent(0, person["telegram_id"], year, "gift"):
                ok, _balance = await change_balance(person["telegram_id"], gift, "birthday",
                                                    note="Подарок Мары на день рождения", chat_id=chat_id)
                given = gift if ok else 0

            try:
                await bot.send_message(chat_id, reminder_text(kind, _mention(person["telegram_id"], person["name"]), given))
                sent += 1
                await asyncio.sleep(0.5)
            except Exception as error:
                logger.warning("BIRTHDAY SEND %s: %s", chat_id, error)

    return sent


async def birthday_loop(bot):
    """Раз в пять минут проверяет живые группы: не пора ли напомнить или поздравить."""
    from database.repository import get_active_chats, get_group_settings
    from settings.store import is_loaded, prime

    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL)
            from settings import access

            for chat_id in await get_active_chats(days=60):
                if not access.allowed(chat_id, "social"):
                    continue
                if not is_loaded(chat_id):
                    try:
                        prime(chat_id, await get_group_settings(chat_id))
                    except Exception:
                        prime(chat_id, {})
                try:
                    await run_reminders(bot, chat_id)
                except Exception as error:
                    logger.warning("BIRTHDAY %s: %s %s", chat_id, type(error).__name__, error)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.error("BIRTHDAY LOOP: %s %s", type(error).__name__, error)
