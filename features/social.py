"""
Пара дня и браки.

Пара дня: «пара дня» или /pair. Мара выбирает двоих из тех, кто писал
за последние N дней. Спрашивать можно сколько угодно раз — каждый раз
новая пара, подряд одна и та же не выпадает.

Браки: /marry (или «выходи за меня») в ответ на сообщение — предложение
с кнопками. Отвечать может только тот, кому предложили. Брак один на все
группы с Марой. После свадьбы Мара выдаёт свидетельство о браке.
/marriage — кто с кем и сколько дней вместе (брак виден в любой группе),
/marriages или «Мара, пары» — пары группы: поженившиеся здесь и любые супруги,
которые оба состоят в этой группе (брак заключён в другой). У каждой — кнопка со
свидетельством (картинкой). /divorce — развод с подтверждением.

Telegram считает командой только латиницу, поэтому русские варианты
ловятся как текст.
"""

import asyncio
import logging
import random
import re
import time
from datetime import datetime
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
)

import audit

from botcontext import TRIGGER_RE, display_name_of

from settings.store import get_number, is_enabled


logger = logging.getLogger("maruska.social")

router = Router(name="social")

PROPOSAL_TTL = 600          # секунд на ответ
RING_ITEM = "diamond_ring"

# «Мара, пары», «Мара, браки», «Мара, список пар» — после обращения к Маре
COUPLES_RE = re.compile(r"^[\s,.!:—-]*(?:все\s+|список\s+)?(?:пары|пар|браки|супруги)\s*[!?.]*\s*$", re.IGNORECASE)

PAIR_RE = re.compile(r"^\s*/?\s*пара\s+дня\s*[!?.]*\s*$", re.IGNORECASE)
MARRY_RE = re.compile(r"^\s*/?\s*(брак|пожениться|выходи\s+за\s+меня|будь\s+мо(ей|им)(\s+(женой|мужем))?)\s*[!?.]*\s*$", re.IGNORECASE)

PAIR_PHRASES = (
    "💞 Пара дня: {a} и {b}! Совет да любовь 🥂",
    "💘 Звёзды сошлись: сегодня {a} + {b} = ❤️",
    "🌹 Купидон целился в потолок, но попал в {a} и {b}. Пара дня!",
    "💑 {a} и {b}, сегодня вы пара. Возражения не принимаются",
    "✨ Мара посмотрела в хрустальный шар: пара дня — {a} и {b}",
    "🍷 По мнению Мары, {a} и {b} сегодня идеально смотрятся вместе",
)

# (чат, кто, кому) -> время предложения
_proposals: dict[tuple[int, int, int], float] = {}

# Последняя пара в чате — чтобы два запроса подряд не дали одну и ту же
_last_pair: dict[int, frozenset[int]] = {}


# ---------------------------------------------------------
# Чистые функции — покрыты тестами
# ---------------------------------------------------------

def is_pair_request(text: str | None) -> bool:
    """«пара дня», «/пара дня» и с обращением: «Мара, пара дня?»."""
    if not text:
        return False
    found = TRIGGER_RE.match(text.strip())
    if found is not None:
        text = text.strip()[found.end():].lstrip(" ,.!:—-")
    return PAIR_RE.match(text) is not None


def is_marry_request(text: str | None) -> bool:
    return bool(text) and MARRY_RE.match(text) is not None


def plural_days(n: int) -> str:
    tail = n % 100
    if 11 <= tail <= 14:
        return "дней"
    return {1: "день", 2: "дня", 3: "дня", 4: "дня"}.get(n % 10, "дней")


def days_together(since: datetime, now: datetime) -> int:
    """Первый день брака считается днём 1 — «вместе 1 день», а не 0."""
    return max((now.date() - since.date()).days, 0) + 1


def choose_pair(candidates: list[dict], exclude: set[int], rng=random) -> tuple[dict, dict] | None:
    pool = [c for c in candidates if c["telegram_id"] not in exclude]
    if len(pool) < 2:
        return None
    first, second = rng.sample(pool, 2)
    return first, second


def mention(user_id: int, name: str) -> str:
    return f'<a href="tg://user?id={user_id}">{escape(name)}</a>'


def proposal_alive(created: float | None, now: float, ttl: int = PROPOSAL_TTL) -> bool:
    return created is not None and now - created <= ttl


# ---------------------------------------------------------
# Пара дня
# ---------------------------------------------------------

async def pair_of_day(message: Message) -> None:
    chat_id = message.chat.id

    if message.chat.type not in ("group", "supergroup"):
        await message.reply("💞 Пара дня выбирается в группах.")
        return

    if not is_enabled(chat_id, "pair_of_day"):
        await message.reply("💞 Пара дня в этой группе выключена (/settings).")
        return

    from database.repository import member_name, pick_candidates

    candidates = await pick_candidates(chat_id, get_number(chat_id, "pair_active_days") or 7)
    me = await message.bot.me()
    chosen = None

    # Несколько попыток, чтобы не повторить прошлую пару (если людей больше двух)
    for _ in range(6):
        chosen = choose_pair(candidates, {me.id})
        if chosen is None or frozenset((chosen[0]["telegram_id"], chosen[1]["telegram_id"])) != _last_pair.get(chat_id):
            break

    if chosen is None:
        await message.reply("💞 Для пары дня нужно хотя бы двое активных участников. Пишите больше!")
        return

    a, b = chosen
    _last_pair[chat_id] = frozenset((a["telegram_id"], b["telegram_id"]))

    audit.log("member", "pair_of_day", chat_id=chat_id, actor_kind="bot",
              details=f"{a['name']} + {b['name']}")

    name_a = await member_name(chat_id, a["telegram_id"])
    name_b = await member_name(chat_id, b["telegram_id"])

    text = random.choice(PAIR_PHRASES).format(a=mention(a["telegram_id"], name_a), b=mention(b["telegram_id"], name_b))

    # Своя картинка из коллекции, привязанной к «паре дня», если есть
    import library_core

    image = await library_core.pick(chat_id, library_core.PAIR)

    if image is not None:
        try:
            await message.answer_photo(photo=image["file_id"], caption=text)
            return
        except Exception as error:
            logger.warning("PAIR IMAGE: %s", error)

    await message.answer(text)


@router.message(Command("pair"))
async def pair_command(message: Message):
    await pair_of_day(message)


@router.message(lambda m: m.chat.type in ("group", "supergroup") and is_pair_request(m.text))
async def pair_text(message: Message):
    await pair_of_day(message)


# ---------------------------------------------------------
# Браки
# ---------------------------------------------------------

def _marriages_on(message: Message) -> str | None:
    if message.chat.type not in ("group", "supergroup"):
        return "💍 Браки заключаются в группах."
    if not is_enabled(message.chat.id, "marriages"):
        return "💍 Браки в этой группе выключены (/settings)."
    return None


async def propose(message: Message) -> None:
    problem = _marriages_on(message)
    if problem:
        await message.reply(problem)
        return

    reply = message.reply_to_message
    target = reply.from_user if reply else None
    user = message.from_user

    if target is None:
        await message.reply("💍 Ответь на сообщение того, кому делаешь предложение: /marry")
        return

    if target.is_bot:
        await message.reply("💍 Мара польщена, но она замужем за своей работой 😌")
        return

    if target.id == user.id:
        await message.reply("💍 Любить себя — прекрасно, но брак с собой не заключают 😄")
        return

    from database.repository import active_marriage, has_item

    chat_id = message.chat.id

    mine = await active_marriage(chat_id, user.id)
    if mine is not None and {mine.user1, mine.user2} == {user.id, target.id}:
        # Уже супруги — просто показываем брак и в этой группе
        from database.repository import register_marriage_here

        await register_marriage_here(chat_id, user.id, target.id)
        await message.reply(f"💞 {escape(display_name_of(user))} и {escape(display_name_of(target))} уже супруги! "
                            "Теперь ваш брак виден и в этой группе — «Мара, пары»")
        return

    if mine is not None:
        await message.reply("💍 Ты уже в браке. Сначала /divorce 😉")
        return

    if await active_marriage(chat_id, target.id):
        await message.reply(f"💍 {escape(display_name_of(target))} уже в браке.")
        return

    if is_enabled(chat_id, "marry_ring") and not await has_item(user.id, RING_ITEM):
        await message.reply("💍 Без кольца предложение не делают. Купи 💍 Кольцо в /shop")
        return

    _proposals[(chat_id, user.id, target.id)] = time.monotonic()

    cost = get_number(chat_id, "marry_cost") or 0
    cost_line = f"\nСвадьба стоит {cost} 💎 — заплатит {escape(display_name_of(user))}." if cost else ""

    await message.answer(
        f"💍 {mention(user.id, display_name_of(user))} делает предложение "
        f"{mention(target.id, display_name_of(target))}!{cost_line}\n\nОтвет — в течение 10 минут.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="💍 Да!", callback_data=f"marry:yes:{user.id}:{target.id}"),
            InlineKeyboardButton(text="💔 Нет", callback_data=f"marry:no:{user.id}:{target.id}"),
        ]]),
    )


@router.message(Command("marry"))
async def marry_command(message: Message):
    await propose(message)


@router.message(lambda m: m.chat.type in ("group", "supergroup") and m.reply_to_message is not None and is_marry_request(m.text))
async def marry_text(message: Message):
    await propose(message)


@router.callback_query(F.data.startswith("marry:"))
async def marry_answer(callback: CallbackQuery):
    try:
        _, answer, proposer_id, target_id = callback.data.split(":")
        proposer_id, target_id = int(proposer_id), int(target_id)
    except ValueError:
        await callback.answer()
        return

    if callback.from_user.id != target_id:
        await callback.answer("Это предложение не тебе 🙂", show_alert=True)
        return

    chat_id = callback.message.chat.id
    key = (chat_id, proposer_id, target_id)

    if not proposal_alive(_proposals.get(key), time.monotonic()):
        _proposals.pop(key, None)
        await callback.answer("Предложение уже неактуально", show_alert=True)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    _proposals.pop(key, None)

    from database.repository import change_balance, create_marriage, member_name

    name_a = await member_name(chat_id, proposer_id)
    name_b = display_name_of(callback.from_user)

    if answer != "yes":
        await callback.message.edit_text(f"💔 {escape(name_b)} отказывает {escape(name_a)}. Держись!")
        await callback.answer()
        return

    cost = get_number(chat_id, "marry_cost") or 0

    if cost:
        ok, _balance = await change_balance(
            telegram_id=proposer_id, amount=-cost, reason="purchase",
            note="Свадьба", chat_id=chat_id, allow_negative=False,
        )
        if not ok:
            await callback.message.edit_text(f"💸 У {escape(name_a)} не хватило {cost} 💎 на свадьбу. Копите!")
            await callback.answer()
            return

    marriage_id = await create_marriage(chat_id, proposer_id, target_id)
    if not marriage_id:
        if cost:
            await change_balance(telegram_id=proposer_id, amount=cost, reason="admin",
                                 note="Возврат: свадьба не состоялась", chat_id=chat_id)
        await callback.message.edit_text("💍 Кто-то из вас уже успел вступить в брак. Свадьба отменяется.")
        await callback.answer()
        return

    audit.log("member", "marriage", chat_id=chat_id, actor_kind="system",
              target_id=target_id, target_name=name_b, details=f"{name_a} + {name_b}")

    await callback.message.edit_text(
        f"💍🎉 {mention(proposer_id, name_a)} и {mention(target_id, name_b)} теперь в браке!\n"
        "Горько! 🥂"
    )
    await callback.answer("💍")

    try:
        await send_certificate(callback.message, marriage_id)
    except Exception as error:
        logger.error("CERTIFICATE: %s %s", type(error).__name__, error)


# Свидетельство рисуется ~1 с: больше двух сразу не рисуем
_drawing = asyncio.Semaphore(2)


def _tag(username: str | None) -> str | None:
    return f"@{username}" if username else None


async def certificate_of(marriage_id: int, chat_title: str | None = None) -> dict | None:
    """Снимок для свидетельства: имена и @ники на день свадьбы. Создаётся один раз."""
    from database.repository import get_marriage, people, save_marriage_certificate

    marriage = await get_marriage(marriage_id)
    if marriage is None:
        return None
    if marriage.certificate:
        return marriage.certificate

    info = await people(marriage.chat_id, (marriage.user1, marriage.user2))
    cert = {
        "number": marriage.id,
        "name1": info[marriage.user1]["name"], "name2": info[marriage.user2]["name"],
        "tag1": _tag(info[marriage.user1]["username"]), "tag2": _tag(info[marriage.user2]["username"]),
        "since": marriage.since.isoformat(),
        "group": chat_title,
    }
    await save_marriage_certificate(marriage_id, certificate=cert)
    return cert


def certificate_button(marriage_id: int, text: str = "📜 Свидетельство") -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=f"mcert:{marriage_id}")


def _photo_prefix() -> str:
    # Картинка в Telegram подписана версией оформления: после смены дизайна рисуем заново
    from features import marriage_certificate as mc

    return f"p{mc.VERSION}:"


async def _send_certificate_photo(message: Message, marriage_id: int, caption: str, chat_title: str | None = None) -> None:
    """Свидетельство картинкой: видно сразу, сохранить — долгим нажатием.
    Нарисованная однажды картинка хранится в Telegram и отправляется повторно без перерисовки."""
    from database.repository import get_marriage, save_marriage_certificate
    from features import marriage_certificate as mc

    marriage = await get_marriage(marriage_id)
    if marriage is None:
        return
    prefix = _photo_prefix()
    if (marriage.certificate_file_id or "").startswith(prefix):
        try:
            await message.answer_photo(marriage.certificate_file_id[len(prefix):], caption=caption)
            return
        except Exception as error:
            logger.warning("CERTIFICATE FILE: %s %s", type(error).__name__, error)

    cert = await certificate_of(marriage_id, chat_title)
    if cert is None:
        return
    async with _drawing:
        image = await asyncio.to_thread(mc.jpeg_bytes, cert)
    sent = await message.answer_photo(
        BufferedInputFile(image, filename=f"svidetelstvo-{marriage_id:06d}.jpg"), caption=caption)
    if sent.photo:
        await save_marriage_certificate(marriage_id, file_id=prefix + sent.photo[-1].file_id)


async def send_certificate(message: Message, marriage_id: int) -> None:
    """Сразу после свадьбы — свидетельство картинкой."""
    from features import marriage_certificate as mc

    cert = await certificate_of(marriage_id, message.chat.title)
    if cert is None:
        return
    await _send_certificate_photo(
        message, marriage_id,
        caption=(f"📜 <b>Свидетельство о браке {mc.number_text(marriage_id)}</b>\n"
                 f"Дворец бракосочетаний «Марушка» поздравляет "
                 f"{escape(cert['name1'])} и {escape(cert['name2'])}! 💞\n\n"
                 "Сохранить — долгое нажатие на картинку."),
    )


@router.callback_query(F.data.startswith("mcert:"))
async def certificate_download(callback: CallbackQuery):
    """Кнопка «Свидетельство» в списке пар: присылает свидетельство картинкой."""
    from database.repository import get_marriage
    from features import marriage_certificate as mc

    try:
        marriage_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer()
        return

    marriage = await get_marriage(marriage_id)
    if marriage is None or not marriage.active:
        await callback.answer("Этого брака больше нет 💔", show_alert=True)
        return

    await callback.answer("📜 Готовлю свидетельство…")
    await _send_certificate_photo(callback.message, marriage_id,
                                  caption=f"📜 Свидетельство о браке {mc.number_text(marriage_id)}")


def _person(name: str, username: str | None) -> str:
    """Имя и @ник ссылкой — без уведомления, чтобы список пар никого не дёргал."""
    if not username:
        return escape(name)
    return f'{escape(name)} (<a href="https://t.me/{escape(username)}">@{escape(username)}</a>)'


def _short(text: str, limit: int = 14) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def show_marriages(message: Message) -> None:
    problem = _marriages_on(message)
    if problem:
        await message.reply(problem)
        return

    from database.repository import list_marriages

    couples = await list_marriages(message.chat.id)

    if not couples:
        await message.reply("💍 В группе пока нет пар. /marry — сделать предложение")
        return

    now = datetime.utcnow()
    lines = ["💞 <b>Пары группы</b>\n"]
    buttons = []

    for place, c in enumerate(couples[:20], start=1):
        days = days_together(datetime.fromisoformat(c["since"]), now)
        lines.append(f"{place}. {_person(c['name1'], c.get('username1'))} 💞 "
                     f"{_person(c['name2'], c.get('username2'))} — {days} {plural_days(days)}")
        buttons.append(certificate_button(c["id"], f"📜 {place}. {_short(c['name1'])} & {_short(c['name2'])}"))

    lines.append("\n📜 Свидетельство пары — кнопкой ниже")
    await message.reply(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[buttons[i:i + 2] for i in range(0, len(buttons), 2)]),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


def is_couples_request(message: Message) -> bool:
    text = message.text or ""
    if message.chat.type not in ("group", "supergroup") or text.startswith("/"):
        return False
    found = TRIGGER_RE.search(text)
    return found is not None and COUPLES_RE.match(text[found.end():]) is not None


@router.message(is_couples_request)
async def couples_text(message: Message):
    await show_marriages(message)


async def marriage_line(chat_id: int, user_id: int) -> str | None:
    """«💍 В браке с Юлей — 25 дней» для профиля. Брак виден в любой группе."""
    from database.repository import active_marriage, member_name

    marriage = await active_marriage(chat_id, user_id)
    if marriage is None:
        return None
    partner = marriage.user2 if marriage.user1 == user_id else marriage.user1
    days = days_together(marriage.since, datetime.utcnow())
    return f"💍 В браке с <b>{escape(await member_name(chat_id, partner))}</b> — {days} {plural_days(days)}"


async def _status_text(chat_id: int, user_id: int, name: str) -> str:
    from database.repository import active_marriage, member_name

    marriage = await active_marriage(chat_id, user_id)

    if marriage is None:
        return f"💍 {escape(name)} пока не в браке."

    partner = marriage.user2 if marriage.user1 == user_id else marriage.user1
    partner_name = await member_name(chat_id, partner)
    days = days_together(marriage.since, datetime.utcnow())

    return (f"💞 {escape(name)} и {escape(partner_name)} вместе {days} {plural_days(days)} "
            f"(с {marriage.since:%d.%m.%Y})")


@router.message(Command("marriage"))
async def marriage_status(message: Message):
    problem = _marriages_on(message)
    if problem:
        await message.reply(problem)
        return

    who = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    await message.reply(await _status_text(message.chat.id, who.id, display_name_of(who)))


@router.message(Command("marriages"))
async def marriages_list(message: Message):
    await show_marriages(message)


@router.message(Command("divorce"))
async def divorce(message: Message):
    problem = _marriages_on(message)
    if problem:
        await message.reply(problem)
        return

    from database.repository import active_marriage

    if await active_marriage(message.chat.id, message.from_user.id) is None:
        await message.reply("💍 Ты и так не в браке.")
        return

    await message.reply(
        "💔 Точно развод?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="💔 Да, развод", callback_data=f"divorce:yes:{message.from_user.id}"),
            InlineKeyboardButton(text="Передумать", callback_data=f"divorce:no:{message.from_user.id}"),
        ]]),
    )


@router.callback_query(F.data.startswith("divorce:"))
async def divorce_answer(callback: CallbackQuery):
    try:
        _, answer, user_id = callback.data.split(":")
        user_id = int(user_id)
    except ValueError:
        await callback.answer()
        return

    if callback.from_user.id != user_id:
        await callback.answer("Это не твой брак 🙂", show_alert=True)
        return

    if answer != "yes":
        await callback.message.edit_text("💞 Брак спасён!")
        await callback.answer()
        return

    from database.repository import end_marriage, member_name

    chat_id = callback.message.chat.id
    pair = await end_marriage(chat_id, user_id)

    if pair is None:
        await callback.message.edit_text("💍 Брака уже нет.")
        await callback.answer()
        return

    a, b = await member_name(chat_id, pair[0]), await member_name(chat_id, pair[1])

    audit.log("member", "divorce", chat_id=chat_id, actor_kind="system",
              target_id=user_id, details=f"{a} + {b}")

    await callback.message.edit_text(f"💔 {escape(a)} и {escape(b)} развелись. Бывает…")
    await callback.answer()
