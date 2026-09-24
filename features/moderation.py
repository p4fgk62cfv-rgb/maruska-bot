"""
Модерация: мут, бан, выкинуть, закрыть чат.

Это НЕ то же самое, что «игнорировать ботом». Игнор лишь заставляет
Мару не слышать человека, а здесь — настоящие ограничения Telegram:
человек перестаёт писать в группу или вылетает из неё.

Чтобы это работало, бот должен быть администратором группы
с правом ограничивать участников. Если прав нет, функции честно
об этом скажут, а не молча ничего не сделают.

Одно ядро обслуживает и панель, и команды в чате.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import ChatPermissions, Message

import audit

from botcontext import display_name_of
from i18n import t

from settings.handler import ADMIN_STATUSES, is_owner
from settings.store import get_number, is_enabled


logger = logging.getLogger("maruska.moderation")

router = Router(name="moderation")


# Разрешения «всё можно» — для размута, если у группы не удалось
# прочитать её собственные настройки по умолчанию
FULL_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_invite_users=True,
)

SILENT = ChatPermissions(
    can_send_messages=False,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
)


class ModerationError(Exception):
    """Понятное человеку сообщение о том, почему не вышло."""


def _explain(error: Exception) -> ModerationError:
    text = str(error).lower()

    if "not enough rights" in text or "need administrator" in text:
        return ModerationError(
            "У меня нет прав. Сделайте меня администратором группы "
            "с правом ограничивать участников."
        )

    if "user is an administrator" in text or "can't restrict self" in text:
        return ModerationError("Администраторов ограничивать нельзя.")

    if "participant_id_invalid" in text or "user not found" in text:
        return ModerationError("Этого человека нет в группе.")

    return ModerationError("Telegram не дал это сделать.")


# ---------------------------------------------------------
# Ядро
# ---------------------------------------------------------

async def mute(bot, chat_id: int, user_id: int, minutes: int) -> None:
    until = datetime.now(timezone.utc) + timedelta(minutes=max(minutes, 1))

    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=SILENT,
            until_date=until,
        )
    except Exception as error:
        raise _explain(error)


async def unmute(bot, chat_id: int, user_id: int) -> None:
    # Возвращаем то, что разрешено группе по умолчанию, а не «всё»:
    # иначе человек получил бы больше прав, чем остальные
    permissions = FULL_PERMISSIONS

    try:
        chat = await bot.get_chat(chat_id)

        if chat.permissions:
            permissions = chat.permissions
    except Exception:
        pass

    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=permissions,
        )
    except Exception as error:
        raise _explain(error)


async def ban(bot, chat_id: int, user_id: int) -> None:
    try:
        await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
    except Exception as error:
        raise _explain(error)


async def unban(bot, chat_id: int, user_id: int) -> None:
    try:
        await bot.unban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            only_if_banned=True,
        )
    except Exception as error:
        raise _explain(error)


async def tempban(bot, chat_id: int, user_id: int, minutes: int) -> None:
    """Бан на время: Telegram сам снимет его по истечении срока."""
    until = datetime.now(timezone.utc) + timedelta(minutes=max(minutes, 1))

    try:
        await bot.ban_chat_member(chat_id=chat_id, user_id=user_id, until_date=until)
    except Exception as error:
        raise _explain(error)


async def kick(bot, chat_id: int, user_id: int) -> None:
    """
    Выкинуть без бана: бан и тут же разбан — человек сможет вернуться
    по ссылке.
    """
    await ban(bot, chat_id, user_id)
    await unban(bot, chat_id, user_id)


async def set_chat_locked(bot, chat_id: int, locked: bool) -> None:
    """
    Закрыть чат — писать могут только администраторы.
    """
    try:
        await bot.set_chat_permissions(
            chat_id=chat_id,
            permissions=SILENT if locked else FULL_PERMISSIONS,
        )
    except Exception as error:
        raise _explain(error)


async def is_chat_locked(bot, chat_id: int) -> bool | None:
    try:
        chat = await bot.get_chat(chat_id)
    except Exception:
        return None

    if chat.permissions is None:
        return None

    return not chat.permissions.can_send_messages


# ---------------------------------------------------------
# Команды в чате
# ---------------------------------------------------------

async def _is_chat_admin(message: Message) -> bool:
    if message.from_user is None:
        return False

    if is_owner(message.from_user.id):
        return True

    try:
        member = await message.bot.get_chat_member(
            message.chat.id,
            message.from_user.id,
        )
    except Exception:
        return False

    return member.status in ADMIN_STATUSES


async def _check(message: Message) -> bool:
    """
    Общие проверки для всех команд модерации.
    """
    if message.chat.type not in ("group", "supergroup"):
        await message.reply("🛡 Модерация работает только в группах.")
        return False

    if not is_enabled(message.chat.id, "moderation"):
        await message.reply(
            "🛡 Модерация в этой группе выключена (/settings)."
        )
        return False

    if not await _is_chat_admin(message):
        await message.reply("🛡 Это только для администраторов группы.")
        return False

    return True


def _record(message: Message, action: str, target=None, details: str | None = None, counter: str | None = None):
    audit.log(
        "moderation", action, chat_id=message.chat.id,
        actor_kind="admin", actor_id=message.from_user.id,
        actor_name=display_name_of(message.from_user),
        target_id=target.id if target else None,
        target_name=display_name_of(target) if target else None,
        details=details,
    )

    if counter:
        audit.count(message.chat.id, counter)


def _target(message: Message):
    reply = message.reply_to_message

    if reply is None or reply.from_user is None or reply.from_user.is_bot:
        return None

    return reply.from_user


MAX_MUTE_MINUTES = 60 * 24 * 30      # месяц

DURATION_RE = re.compile(
    r"^(\d{1,4})\s*(м|мин|m|min|ч|час|h|д|дн|день|дней|d)?$",
    re.IGNORECASE,
)

UNIT_MINUTES = {
    "": 1, "м": 1, "мин": 1, "m": 1, "min": 1,
    "ч": 60, "час": 60, "h": 60,
    "д": 1440, "дн": 1440, "день": 1440, "дней": 1440, "d": 1440,
}


def parse_duration(text: str) -> int | None:
    """
    "30" → 30 минут, "2ч" → 120, "1д" → 1440, "2h" → 120.
    """
    match = DURATION_RE.match((text or "").strip().lower())

    if not match:
        return None

    value = int(match.group(1))
    unit = UNIT_MINUTES.get(match.group(2) or "", 1)

    return max(1, min(value * unit, MAX_MUTE_MINUTES))


def _minutes(message: Message) -> int:
    parts = (message.text or "").split()

    # Число и единица могут быть слитно или через пробел: "2ч" и "2 ч"
    joined = " ".join(parts[1:3])

    for candidate in (joined, *parts[1:]):
        parsed = parse_duration(candidate)
        if parsed:
            return parsed

    return get_number(message.chat.id, "mute_minutes") or 60


def _plural_minutes(value: int) -> str:
    if value >= 1440 and value % 1440 == 0:
        return f"{value // 1440} дн."

    if value >= 60 and value % 60 == 0:
        return f"{value // 60} ч"

    return f"{value} мин"


@router.message(Command("mute"))
async def mute_command(message: Message):
    if not await _check(message):
        return

    target = _target(message)

    if target is None:
        await message.reply(
            "🔇 Ответь на сообщение человека:\n"
            "<code>/mute 30</code> — 30 минут\n"
            "<code>/mute 2ч</code> — 2 часа\n"
            "<code>/mute 1д</code> — сутки\n"
            "Без времени — сколько задано в настройках."
        )
        return

    minutes = _minutes(message)

    try:
        await mute(message.bot, message.chat.id, target.id, minutes)
    except ModerationError as error:
        await message.reply(f"⚠️ {error}")
        return

    _record(message, "mute", target, _plural_minutes(minutes), "mutes")

    await message.answer(
        t(message.chat.id, "cmd.mute", name=escape(display_name_of(target)), span=_plural_minutes(minutes))
    )


@router.message(Command("unmute"))
async def unmute_command(message: Message):
    if not await _check(message):
        return

    target = _target(message)

    if target is None:
        await message.reply("🔊 Ответь на сообщение человека: <code>/unmute</code>")
        return

    try:
        await unmute(message.bot, message.chat.id, target.id)
    except ModerationError as error:
        await message.reply(f"⚠️ {error}")
        return

    _record(message, "unmute", target)

    await message.answer(
        t(message.chat.id, "cmd.unmute", name=escape(display_name_of(target)))
    )


@router.message(Command("ban"))
async def ban_command(message: Message):
    if not await _check(message):
        return

    target = _target(message)

    if target is None:
        await message.reply("⛔ Ответь на сообщение человека: <code>/ban</code>")
        return

    try:
        await ban(message.bot, message.chat.id, target.id)
    except ModerationError as error:
        await message.reply(f"⚠️ {error}")
        return

    _record(message, "ban", target, counter="bans")

    await message.answer(
        t(message.chat.id, "cmd.ban", name=escape(display_name_of(target)))
    )


@router.message(Command("unban"))
async def unban_command(message: Message):
    if not await _check(message):
        return

    target = _target(message)

    if target is None:
        await message.reply(
            "✅ Ответь на сообщение человека: <code>/unban</code>\n"
            "Или разбань из веб-панели — там есть список."
        )
        return

    try:
        await unban(message.bot, message.chat.id, target.id)
    except ModerationError as error:
        await message.reply(f"⚠️ {error}")
        return

    _record(message, "unban", target)

    await message.answer(
        t(message.chat.id, "cmd.unban", name=escape(display_name_of(target)))
    )


@router.message(Command("kick"))
async def kick_command(message: Message):
    if not await _check(message):
        return

    target = _target(message)

    if target is None:
        await message.reply("👢 Ответь на сообщение человека: <code>/kick</code>")
        return

    try:
        await kick(message.bot, message.chat.id, target.id)
    except ModerationError as error:
        await message.reply(f"⚠️ {error}")
        return

    _record(message, "kick", target)

    await message.answer(t(message.chat.id, "cmd.kick", name=escape(display_name_of(target))))


@router.message(Command("lock", "close"))
async def lock_command(message: Message):
    if not await _check(message):
        return

    try:
        await set_chat_locked(message.bot, message.chat.id, True)
    except ModerationError as error:
        await message.reply(f"⚠️ {error}")
        return

    _record(message, "lock")

    await message.answer(t(message.chat.id, "cmd.lock"))


@router.message(Command("unlock", "open"))
async def unlock_command(message: Message):
    if not await _check(message):
        return

    try:
        await set_chat_locked(message.bot, message.chat.id, False)
    except ModerationError as error:
        await message.reply(f"⚠️ {error}")
        return

    _record(message, "unlock")

    await message.answer(t(message.chat.id, "cmd.unlock"))


@router.message(Command("warn"))
async def warn_command(message: Message):
    if not await _check(message):
        return

    target = _target(message)

    if target is None:
        await message.reply(
            "⚠️ Ответь на сообщение человека: <code>/warn причина</code>\n"
            "После лимита предупреждений сработает наказание из настроек."
        )
        return

    parts = (message.text or "").split(maxsplit=1)
    reason = parts[1].strip()[:120] if len(parts) > 1 else "предупреждение от админа"

    from features.automod import warn

    await warn(
        message.bot, message.chat.id, target.id, display_name_of(target), reason,
        actor_kind="admin", actor_id=message.from_user.id,
        actor_name=display_name_of(message.from_user),
        notify=message.answer,
    )


@router.message(Command("tban"))
async def tempban_command(message: Message):
    if not await _check(message):
        return

    target = _target(message)

    if target is None:
        await message.reply(
            "⏳ Ответь на сообщение человека: <code>/tban 1д</code>\n"
            "Бан на время — потом человек сможет вернуться."
        )
        return

    minutes = _minutes(message)

    try:
        await tempban(message.bot, message.chat.id, target.id, minutes)
    except ModerationError as error:
        await message.reply(f"⚠️ {error}")
        return

    _record(message, "tempban", target, _plural_minutes(minutes), "bans")

    await message.answer(
        t(message.chat.id, "cmd.tempban", name=escape(display_name_of(target)), span=_plural_minutes(minutes))
    )
