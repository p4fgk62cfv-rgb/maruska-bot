"""
Капча для новичков: «Я не бот».

Новичку на время проверки запрещено писать, бот присылает кнопку.
Нажал вовремя — ограничение снимается. Не нажал — вылетает из
группы (без бана: сможет вернуться и пройти заново).

Ограничение ставится со сроком истечения чуть больше времени на
проверку. Если бот перезапустится посреди проверки, человек не
останется замученным навсегда — Telegram снимет мут сам.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

import audit

from botcontext import display_name_of
from i18n import t

from settings.store import get_number, is_enabled


logger = logging.getLogger("maruska.captcha")

router = Router(name="captcha")

# (чат, человек) -> (задача таймера, id сообщения с кнопкой)
_pending: dict[tuple[int, int], tuple[asyncio.Task, int]] = {}


async def start_captcha(bot, chat_id: int, users) -> None:
    if not is_enabled(chat_id, "captcha"):
        return

    from features.moderation import SILENT
    from webapp.roles import bot_rights

    if not (await bot_rights(bot, chat_id)).get("restrict"):
        logger.warning("CAPTCHA %s: нет права ограничивать участников", chat_id)
        return

    minutes = get_number(chat_id, "captcha_minutes") or 3

    for user in users:
        if user.is_bot:
            continue

        until = datetime.now(timezone.utc) + timedelta(minutes=minutes + 1)

        try:
            await bot.restrict_chat_member(chat_id, user.id, permissions=SILENT, until_date=until)
        except Exception as error:
            logger.warning("CAPTCHA RESTRICT %s: %s", user.id, error)
            continue

        name = escape(display_name_of(user))

        try:
            sent = await bot.send_message(
                chat_id,
                t(chat_id, "captcha.ask", name=name, minutes=minutes),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text=t(chat_id, "captcha.button"), callback_data=f"captcha:{user.id}")
                ]]),
            )
        except Exception as error:
            logger.warning("CAPTCHA SEND %s: %s", user.id, error)
            continue

        key = (chat_id, user.id)
        old = _pending.pop(key, None)

        if old:
            old[0].cancel()

        task = asyncio.create_task(_timeout(bot, chat_id, user, sent.message_id, minutes))
        _pending[key] = (task, sent.message_id)


async def _timeout(bot, chat_id: int, user, message_id: int, minutes: int) -> None:
    try:
        await asyncio.sleep(minutes * 60)
    except asyncio.CancelledError:
        return

    if _pending.pop((chat_id, user.id), None) is None:
        return

    from features.moderation import ModerationError, kick

    try:
        await kick(bot, chat_id, user.id)
    except ModerationError as error:
        logger.warning("CAPTCHA KICK %s: %s", user.id, error)
        return

    audit.log(
        "moderation", "captcha_failed", chat_id=chat_id, actor_kind="bot",
        target_id=user.id, target_name=display_name_of(user),
    )

    try:
        await bot.edit_message_text(
            t(chat_id, "captcha.failed", name=escape(display_name_of(user))),
            chat_id=chat_id, message_id=message_id,
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("captcha:"))
async def captcha_press(callback: CallbackQuery):
    chat_id = callback.message.chat.id

    try:
        user_id = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer()
        return

    if callback.from_user.id != user_id:
        await callback.answer(t(chat_id, "captcha.not_you"), show_alert=True)
        return

    pending = _pending.pop((chat_id, user_id), None)

    if pending:
        pending[0].cancel()

    from features.moderation import ModerationError, unmute

    try:
        await unmute(callback.bot, chat_id, user_id)
    except ModerationError as error:
        logger.warning("CAPTCHA UNMUTE %s: %s", user_id, error)

    audit.log(
        "moderation", "captcha_passed", chat_id=chat_id, actor_kind="system",
        target_id=user_id, target_name=display_name_of(callback.from_user),
    )

    try:
        await callback.message.edit_text(
            t(chat_id, "captcha.passed", name=escape(display_name_of(callback.from_user)))
        )
    except Exception:
        pass

    await callback.answer("✅")
