"""
Рейтинг: плюсы и минусы реплаем, «спасибо» в ответ — тоже плюс; топ участников.

Одного и того же человека можно оценить раз в rating_cooldown_minutes (5 минут).
Сообщения Мары об оценке через 10 секунд удаляются, чтобы не засорять чат.
"""

import asyncio
import logging
import re
from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from botcontext import display_name_of, get_rank_info

from database.repository import (
    add_rating_vote,
    can_vote_rating,
    count_inventory,
    get_balance,
    get_global_rating,
    get_profile,
    get_rating_position,
    get_rating_stats,
    save_user,
    create_profile_if_needed,
)

from economy.service import CURRENCY, money, wealth_title

from progress.service import profile_block

from settings.store import get_number, is_enabled

logger = logging.getLogger("maruska.rating")

router = Router(name="rating")

# Сообщение Мары об оценке живёт столько секунд, потом удаляется
NOTICE_TTL = 10

PLUS = {"+", "＋"}
MINUS = {"-", "−"}

# Короткое «спасибо» в ответ на сообщение: «спасибо!», «спс», «благодарю», «спасибо большое 🙏»
_THANKS = re.compile(r"(спасиб|спс|сяп|пасиб|благодар|thank|thx)", re.IGNORECASE)
_WORDS = re.compile(r"[^\W\d_]+")


def is_thanks(text: str | None) -> bool:
    if not text or len(text) > 40:
        return False
    words = _WORDS.findall(text)
    # «Мара, спасибо» — это спасибо Маре, а не человеку из реплая
    if any(w.lower().startswith(("мар", "maru", "mara")) for w in words):
        return False
    return 0 < len(words) <= 4 and bool(_THANKS.search(text))


def is_rating_message(message: Message) -> bool:
    if not is_enabled(message.chat.id, "rating") or message.text is None:
        return False

    text = message.text.strip()
    if text in PLUS or text in MINUS:
        return True
    # «Спасибо» считается плюсом, только если это ответ живому человеку
    reply = message.reply_to_message
    return (
        is_thanks(text)
        and reply is not None
        and reply.from_user is not None
        and not reply.from_user.is_bot
    )


_tasks: set[asyncio.Task] = set()


async def _delete_later(message: Message, delay: int) -> None:
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass


async def notice(message: Message, text: str) -> None:
    """Ответ Мары про рейтинг: через NOTICE_TTL секунд он исчезает."""
    sent = await message.reply(text)
    task = asyncio.create_task(_delete_later(sent, NOTICE_TTL))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def cooldown_text(minutes: int) -> str:
    if minutes % 60 == 0:
        return f"{minutes // 60} ч."
    return f"{minutes} мин."


@router.message(is_rating_message)
async def rating_handler(message: Message):
    if not message.from_user or not message.reply_to_message:
        return

    target = message.reply_to_message.from_user

    if target is None or target.is_bot:
        return

    text = message.text.strip()
    thanks = text not in PLUS and text not in MINUS

    if target.id == message.from_user.id:
        if not thanks:
            await notice(message, "😏 Себе рейтинг накручивать нельзя.")
        return

    amount = -1 if text in MINUS else 1

    await save_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    await save_user(
        telegram_id=target.id,
        username=target.username,
        first_name=target.first_name,
    )

    cooldown = get_number(message.chat.id, "rating_cooldown_minutes") or 5

    if not await can_vote_rating(
        giver_telegram_id=message.from_user.id,
        target_telegram_id=target.id,
        cooldown_minutes=cooldown,
    ):
        # На частое «спасибо» молчим: это обычный разговор, а не накрутка
        if not thanks:
            await notice(message, f"⏳ Этого пользователя можно оценить снова через {cooldown_text(cooldown)}")
        return

    target_name = display_name_of(target)

    new_rating = await add_rating_vote(
        giver_telegram_id=message.from_user.id,
        target_telegram_id=target.id,
        amount=amount,
        display_name=target_name,
    )

    name = escape(target_name)
    rank = get_rank_info(new_rating)

    if amount > 0:
        await notice(
            message,
            f"{'🙏 <b>Спасибо!</b>' if thanks else '❤️ <b>Лайк!</b>'}\n\n"
            f"Рейтинг пользователя <b>{name}</b> повышен на <b>+1</b>.\n\n"
            f"⭐ Теперь рейтинг: <b>{new_rating}</b>\n"
            f"🎖 Ранг: <b>{rank}</b>"
        )
    else:
        await notice(
            message,
            f"💔 <b>Минус!</b>\n\n"
            f"Рейтинг пользователя <b>{name}</b> понижен на <b>-1</b>.\n\n"
            f"⭐ Теперь рейтинг: <b>{new_rating}</b>\n"
            f"🎖 Ранг: <b>{rank}</b>"
        )


# =========================================================
# TOP
# =========================================================

@router.message(Command("top"))
async def top_handler(message: Message):
    if not is_enabled(message.chat.id, "rating"):
        await message.reply("⭐ Рейтинг в этой группе выключен (/settings).")
        return

    users = await get_global_rating(limit=10)

    if not users:
        await message.answer("🏆 Пока рейтинг пуст.")
        return

    lines = ["🏆 <b>Глобальный рейтинг</b>\n"]
    medals = ["🥇", "🥈", "🥉"]

    for index, user in enumerate(users, start=1):
        medal = medals[index - 1] if index <= 3 else f"{index}."
        name = escape(user.display_name or "Пользователь")
        lines.append(
            f"{medal} <b>{name}</b> — {user.karma} ⭐ "
            f"({get_rank_info(user.karma)})"
        )

    await message.answer("\n".join(lines))



async def profile_card(chat_id: int, telegram_id: int, name: str | None = None, create: bool = False) -> str | None:
    """Карточка человека: брак, уровень, рейтинг, алмазы, сообщения, игры, оценки.
    Её показывают /profile и «Мара, кто я?» — у каждого своя."""
    profile = await get_profile(telegram_id)

    if profile is None and create:
        await create_profile_if_needed(telegram_id=telegram_id, display_name=name)
        profile = await get_profile(telegram_id)

    if profile is None:
        return None

    position = await get_rating_position(telegram_id)
    stats = await get_rating_stats(telegram_id)

    title = escape(profile.display_name or name or "Пользователь")

    levels = ""

    if is_enabled(chat_id, "progress"):
        levels = profile_block(profile.xp or 0) + "\n"

    wallet = ""

    if is_enabled(chat_id, "economy"):
        balance = await get_balance(telegram_id)
        wallet = (
            f"{CURRENCY} Алмазы: <b>{money(balance)}</b> "
            f"({wealth_title(balance)})\n"
        )

        if profile.bonus_streak:
            wallet += f"🔥 Серия бонусов: <b>{profile.bonus_streak}</b>\n"

        collection = await count_inventory(telegram_id)

        if collection:
            wallet += f"🎒 Вещей в инвентаре: <b>{collection}</b>\n"

        wallet += "\n"

    marriage = ""

    if is_enabled(chat_id, "marriages"):
        from features.social import marriage_line

        line = await marriage_line(chat_id, telegram_id)
        if line:
            marriage = line + "\n\n"

    return (
        f"👤 <b>{title}</b>\n\n"
        f"{marriage}"
        f"{levels}"
        f"🎖 Ранг: <b>{get_rank_info(profile.karma)}</b>\n"
        f"⭐ Рейтинг: <b>{profile.karma}</b>\n"
        f"🏆 Место: <b>#{position or '-'}</b>\n\n"
        f"{wallet}"
        f"💬 Сообщений: <b>{profile.messages_count}</b>\n"
        f"🎮 Игр: <b>{profile.games_played}</b>\n"
        f"🏅 Побед: <b>{profile.games_won}</b>\n\n"
        f"❤️ Положительных оценок: <b>{stats['positive']}</b>\n"
        f"💔 Отрицательных оценок: <b>{stats['negative']}</b>"
    )


@router.message(Command("profile"))
async def profile_handler(message: Message):
    """/profile — своя карточка, ответом на сообщение — карточка того человека."""
    if not message.from_user:
        return

    reply = message.reply_to_message
    if reply and reply.from_user and not reply.from_user.is_bot:
        target = reply.from_user
    else:
        target = message.from_user

    card = await profile_card(message.chat.id, target.id, display_name_of(target), create=target.id == message.from_user.id)
    if card is None:
        await message.answer(f"🤷 Про {escape(display_name_of(target))} пока ничего нет — пусть напишет в чат.")
        return
    await message.answer(card)
