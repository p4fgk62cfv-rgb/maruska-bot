"""
Пара дня и браки.

Пара дня: «пара дня» или /pair. Раз в сутки (по часовому поясу
группы) Мара выбирает двоих из тех, кто писал за последние N дней.
Повторный запрос в тот же день показывает ту же пару.

Браки: /marry (или «выходи за меня») в ответ на сообщение — предложение
с кнопками. Отвечать может только тот, кому предложили. /marriage —
кто с кем и сколько дней вместе, /marriages — все пары группы,
/divorce — развод с подтверждением.

Telegram считает командой только латиницу, поэтому русские варианты
ловятся как текст.
"""

import logging
import random
import re
import time
from datetime import datetime
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import audit

from botcontext import display_name_of

from settings.store import get_number, is_enabled, local_now


logger = logging.getLogger("maruska.social")

router = Router(name="social")

PROPOSAL_TTL = 600          # секунд на ответ
RING_ITEM = "diamond_ring"

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


# ---------------------------------------------------------
# Чистые функции — покрыты тестами
# ---------------------------------------------------------

def is_pair_request(text: str | None) -> bool:
    return bool(text) and PAIR_RE.match(text) is not None


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

    from database.repository import get_daily_pick, member_name, pick_candidates, save_daily_pick

    day = local_now(chat_id).strftime("%Y-%m-%d")
    pick = await get_daily_pick(chat_id, day, "pair")
    again = pick is not None

    if pick is None:
        candidates = await pick_candidates(chat_id, get_number(chat_id, "pair_active_days") or 7)
        me = await message.bot.me()
        chosen = choose_pair(candidates, {me.id})

        if chosen is None:
            await message.reply("💞 Для пары дня нужно хотя бы двое активных участников. Пишите больше!")
            return

        phrase = random.choice(PAIR_PHRASES)
        saved = await save_daily_pick(chat_id, day, "pair", chosen[0]["telegram_id"], chosen[1]["telegram_id"], phrase)

        # Двое одновременно запросили — показываем ту пару, что успела сохраниться
        pick = await get_daily_pick(chat_id, day, "pair")
        again = not saved

        if saved:
            audit.log("member", "pair_of_day", chat_id=chat_id, actor_kind="bot",
                      details=f"{chosen[0]['name']} + {chosen[1]['name']}")

    name_a = await member_name(chat_id, pick.user1)
    name_b = await member_name(chat_id, pick.user2)

    text = (pick.phrase or PAIR_PHRASES[0]).format(a=mention(pick.user1, name_a), b=mention(pick.user2, name_b))

    if again:
        text = "Пара дня уже выбрана 😉\n\n" + text + "\n\nСледующая — завтра."

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

    if await active_marriage(chat_id, user.id):
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
        await callback.message.edit_text(f"💔 {escape(name_b)} ответил(а) отказом {escape(name_a)}. Держись!")
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

    if not await create_marriage(chat_id, proposer_id, target_id):
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

    for place, c in enumerate(couples[:20], start=1):
        days = days_together(datetime.fromisoformat(c["since"]), now)
        lines.append(f"{place}. {escape(c['name1'])} 💞 {escape(c['name2'])} — {days} {plural_days(days)}")

    await message.reply("\n".join(lines))


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
            InlineKeyboardButton(text="Передумал(а)", callback_data=f"divorce:no:{message.from_user.id}"),
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
