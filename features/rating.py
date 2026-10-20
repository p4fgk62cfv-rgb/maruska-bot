"""
Рейтинг: плюсы и минусы реплаем, топ участников.
"""

import logging
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


def is_rating_message(message: Message) -> bool:
    if not is_enabled(message.chat.id, "rating"):
        return False

    return (
        message.text is not None
        and message.text.strip() in {"+", "-", "＋", "−"}
    )


@router.message(is_rating_message)
async def rating_handler(message: Message):
    if not message.from_user or not message.reply_to_message:
        return

    target = message.reply_to_message.from_user

    if target is None or target.is_bot:
        return

    if target.id == message.from_user.id:
        await message.reply("😏 Себе рейтинг накручивать нельзя.")
        return

    amount = 1 if message.text.strip() in {"+", "＋"} else -1

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

    cooldown = get_number(message.chat.id, "rating_cooldown") or 24

    if not await can_vote_rating(
        giver_telegram_id=message.from_user.id,
        target_telegram_id=target.id,
        cooldown_hours=cooldown,
    ):
        await message.reply(
            f"⏳ Этого пользователя можно оценить снова через {cooldown} ч."
        )
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
        await message.reply(
            f"❤️ <b>Лайк!</b>\n\n"
            f"Рейтинг пользователя <b>{name}</b> повышен на <b>+1</b>.\n\n"
            f"⭐ Теперь рейтинг: <b>{new_rating}</b>\n"
            f"🎖 Ранг: <b>{rank}</b>"
        )
    else:
        await message.reply(
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
