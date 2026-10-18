"""
Приветствие новых участников.

Человека добавили в чат, и он не знает, что бот умеет. Короткое
сообщение с парой команд решает это лучше, чем закреплённый пост,
который никто не читает.
"""

import logging
import random
from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import ChatMemberUpdated, Message

from database.repository import save_user

from settings.registry import DEFAULT_GREETING, DEFAULT_GREETING_HINT

from settings.store import get_text, is_enabled


logger = logging.getLogger("maruska.greeting")

router = Router(name="greeting")


# Стандартные варианты. Если админ задал свой текст в /settings,
# берётся он, а эти нужны только для разнообразия по умолчанию.
GREETINGS = (
    DEFAULT_GREETING,
    "👋 О, новенький! Привет, <b>{name}</b>.",
    "👋 <b>{name}</b> с нами. Уже интересно.",
    "👋 Привет, <b>{name}</b>! Чувствуй себя как дома.",
    "👋 Встречайте: <b>{name}</b>.",
)


def greeting_line(chat_id: int, name: str) -> str:
    """
    Свой текст группы, а если его нет — случайный стандартный.
    """
    from i18n import language, t

    own = get_text(chat_id, "greeting_text")

    if own != DEFAULT_GREETING:
        template = own
    elif language(chat_id) != "ru":
        # Свой текст не задан — стандартный на языке группы
        return t(chat_id, "greet.default", name=name)
    else:
        template = random.choice(GREETINGS)

    # Новичка отмечаем всегда: свой текст без {name} — тег первой строкой
    if "{name}" not in template:
        return f"👋 {name}!\n{template}"

    # Простая замена, а не format: лишние {скобки} в тексте админа не ломают тег
    return template.replace("{name}", name)


def greeting_hint(chat_id: int) -> str:
    from i18n import language, t

    own = get_text(chat_id, "greeting_hint") or DEFAULT_GREETING_HINT

    if own == DEFAULT_GREETING_HINT and language(chat_id) != "ru":
        return t(chat_id, "greet.hint")

    return own


def _name(user) -> str:
    return escape(user.first_name or user.username or "Новенький")


def mention(user) -> str:
    """Имя-ссылка на человека: Telegram подсвечивает его и присылает уведомление."""
    return f'<a href="tg://user?id={user.id}">{_name(user)}</a>'


# О входе Telegram может сообщить дважды: служебным сообщением и
# событием chat_member. Помним недавних, чтобы не считать двойно.
_recent_joins: dict[tuple[int, int], float] = {}


def _fresh_join(chat_id: int, user_id: int) -> bool:
    import time as _time

    now = _time.monotonic()
    key = (chat_id, user_id)

    if now - _recent_joins.get(key, -1e9) < 120:
        return False

    _recent_joins[key] = now

    if len(_recent_joins) > 2000:
        _recent_joins.clear()

    return True


async def track_join(chat_id: int, users) -> list:
    """
    Учёт новичков — всегда, даже если приветствие выключено:
    статистика, журнал, правила для новичков в автомодерации.
    Возвращает тех, кого ещё не учитывали — их и приветствуем.
    """
    import audit
    from features.automod import remember_join
    from database.repository import ensure_member

    people = [
        user for user in users
        if user and not user.is_bot and _fresh_join(chat_id, user.id)
    ]

    for user in people:
        remember_join(chat_id, user.id)
        audit.count(chat_id, "new_users")
        audit.log(
            "member", "join", chat_id=chat_id, actor_kind="system",
            target_id=user.id, target_name=_name(user),
        )

        try:
            await save_user(
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name,
            )
            # Сразу в список участников — не дожидаясь первого сообщения
            await ensure_member(chat_id, user.id, user.first_name or user.username)
        except Exception as error:
            logger.warning("JOIN SAVE: %s", error)

    return people


async def track_leave(chat_id: int, user, kicked: bool) -> None:
    import audit
    from database.repository import mark_member_left

    if user is None or user.is_bot:
        return

    # Отрицательный id — отдельная метка для ухода, чтобы не путать со входом
    if not _fresh_join(chat_id, -user.id):
        return

    _recent_joins.pop((chat_id, user.id), None)

    audit.log(
        "member", "kicked" if kicked else "leave", chat_id=chat_id,
        actor_kind="system", target_id=user.id, target_name=_name(user),
    )

    try:
        await mark_member_left(chat_id, user.id, True)
    except Exception as error:
        logger.warning("LEAVE SAVE: %s", error)


# Видео (или GIF, фото) к приветствию: хранится в настройках группы
# как file_id Telegram — загружают в админке или командой /welcomevideo
MEDIA_KEY = "greeting_media"
MEDIA_KINDS = ("video", "animation", "photo")
CAPTION_LIMIT = 1024


async def greeting_media(chat_id: int) -> dict | None:
    from database.repository import get_group_settings

    try:
        media = (await get_group_settings(chat_id)).get(MEDIA_KEY)
    except Exception as error:
        logger.warning("GREET MEDIA LOAD: %s", error)
        return None

    if isinstance(media, dict) and media.get("kind") in MEDIA_KINDS and media.get("file_id"):
        return media
    return None


async def send_greeting(bot, chat_id: int, text: str, media: dict | None):
    """Приветствие с вложением. Длинный текст в подпись не влезает — тогда вложение, а под ним текст."""
    if media:
        send = {"video": bot.send_video, "animation": bot.send_animation, "photo": bot.send_photo}[media["kind"]]
        fits = len(text) <= CAPTION_LIMIT
        try:
            sent = await send(chat_id, media["file_id"], caption=text if fits else None)
            if fits:
                return sent
        except Exception as error:
            # Видео удалили или file_id устарел — поздороваемся хотя бы текстом
            logger.warning("GREET MEDIA SEND: %s %s", type(error).__name__, error)

    return await bot.send_message(chat_id, text)


async def welcome(bot, chat_id: int, users) -> None:
    people = [user for user in users if user and not user.is_bot]

    if not people:
        return

    if len(people) == 1:
        head = greeting_line(chat_id, mention(people[0]))
    else:
        names = ", ".join(f"<b>{mention(user)}</b>" for user in people)
        head = f"👋 Пополнение: {names}"

    try:
        await send_greeting(bot, chat_id, f"{head}\n\n{greeting_hint(chat_id)}", await greeting_media(chat_id))
    except Exception as error:
        logger.warning("GREET SEND: %s %s", type(error).__name__, error)


def media_of(message: Message) -> dict | None:
    """Вложение сообщения в виде, в каком его хранит приветствие."""
    if message.animation:
        return {"kind": "animation", "file_id": message.animation.file_id, "name": message.animation.file_name or "GIF"}
    if message.video:
        return {"kind": "video", "file_id": message.video.file_id, "name": message.video.file_name or "видео"}
    if message.photo:
        return {"kind": "photo", "file_id": message.photo[-1].file_id, "name": "фото"}
    return None


@router.message(Command("welcomevideo", "greetvideo"))
async def welcome_video_command(message: Message, command: CommandObject):
    """
    Админ отвечает этой командой на видео, GIF или фото — оно прикрепляется к приветствию.
    «/welcomevideo off» — убрать.
    """
    from database.repository import set_group_setting
    from settings.handler import GROUP_CHATS, is_admin

    if message.chat.type not in GROUP_CHATS:
        await message.answer("Команда работает в группе: ответь ей на видео, которое нужно новичкам.")
        return

    if not await is_admin(message, message.bot):
        return

    if (command.args or "").strip().lower() in ("off", "выкл", "убрать", "нет"):
        await set_group_setting(chat_id=message.chat.id, key=MEDIA_KEY, value=None)
        await message.reply("👌 Видео убрано — приветствие снова только текстом.")
        return

    media = media_of(message.reply_to_message) if message.reply_to_message else None

    if media is None:
        await message.reply(
            "🎬 Ответь этой командой на видео, GIF или фото — прикреплю его к приветствию новичков.\n"
            "Убрать: <code>/welcomevideo off</code>"
        )
        return

    await set_group_setting(chat_id=message.chat.id, key=MEDIA_KEY, value=media)
    await message.reply("✅ Готово! Теперь новичков встречаю с этим вложением. Убрать: <code>/welcomevideo off</code>")


@router.message(F.new_chat_members)
async def new_members(message: Message):
    """
    Классическое служебное сообщение о добавлении участника.
    """
    me = await message.bot.me()

    # Если добавили самого бота — здороваемся с чатом, а не с собой
    added_self = any(
        user.id == me.id for user in (message.new_chat_members or [])
    )

    fresh = [] if added_self else await track_join(message.chat.id, message.new_chat_members or [])

    if fresh:
        from features.captcha import start_captcha

        await start_captcha(message.bot, message.chat.id, fresh)

    if not is_enabled(message.chat.id, "greeting"):
        return

    if added_self:
        await message.answer(
            "👋 Всем привет! Я Мара.\n\n"
            + greeting_hint(message.chat.id)
            + "\n\n⚙️ <code>/settings</code> — что включить, "
            "а что выключить (для админов)"
        )
        return

    if fresh:
        await welcome(message.bot, message.chat.id, fresh)


@router.message(F.left_chat_member)
async def member_left(message: Message):
    user = message.left_chat_member
    kicked = message.from_user is not None and user is not None and message.from_user.id != user.id

    await track_leave(message.chat.id, user, kicked=kicked)


@router.chat_member()
async def member_joined(event: ChatMemberUpdated):
    """
    Современный способ: Telegram присылает это событие, даже когда
    человек зашёл сам по ссылке-приглашению.
    """
    was = event.old_chat_member.status
    now = event.new_chat_member.status

    joined = was in ("left", "kicked") and now in ("member", "administrator", "restricted")
    left = was in ("member", "administrator", "restricted") and now in ("left", "kicked")

    if left:
        await track_leave(event.chat.id, event.new_chat_member.user, kicked=now == "kicked")
        return

    if not joined:
        return

    fresh = await track_join(event.chat.id, [event.new_chat_member.user])

    if fresh:
        from features.captcha import start_captcha

        await start_captcha(event.bot, event.chat.id, fresh)

    if not fresh or not is_enabled(event.chat.id, "greeting"):
        return

    await welcome(event.bot, event.chat.id, fresh)


@router.my_chat_member()
async def bot_added(event: ChatMemberUpdated):
    """
    Мару добавили в группу (или сделали админом). Группа сразу появляется в панели:
    раньше она считалась «знакомой» только после первого сообщения, и админ новой
    группы видел «Нет доступа».
    """
    if event.chat.type not in ("group", "supergroup"):
        return
    now = event.new_chat_member.status
    if now in ("left", "kicked"):
        # Мару удалили — группа пропадает из панели (вернут — появится снова)
        from database.repository import mark_chat_gone

        try:
            await mark_chat_gone(event.chat.id)
        except Exception as error:
            logger.warning("BOT REMOVED: %s", error)
        return
    if now not in ("member", "administrator"):
        return

    from database.repository import ensure_member, remember_chat
    from webapp.admin import drop_access_cache

    chat_id = event.chat.id
    try:
        await remember_chat(chat_id, event.chat.title)
        people = []
        if event.from_user and not event.from_user.is_bot:
            people.append(event.from_user)
        try:
            admins = await event.bot.get_chat_administrators(chat_id)
            people += [m.user for m in admins if not m.user.is_bot]
        except Exception as error:
            logger.warning("ADMINS on join: %s", error)
        for user in people:
            await ensure_member(chat_id, user.id, user.first_name or user.username)
            drop_access_cache(user.id)
    except Exception as error:
        logger.warning("BOT ADDED: %s", error)


@router.message(F.migrate_to_chat_id)
async def group_upgraded(message: Message):
    """
    Обычную группу сделали супергруппой (история чата, публичная ссылка…).
    Telegram даёт ей новый ID — переносим всё, что Мара о ней знает.
    """
    from database.repository import move_chat
    from settings import store

    old_id, new_id = message.chat.id, message.migrate_to_chat_id
    try:
        await move_chat(old_id, new_id)
        store.forget(old_id)
        store.forget(new_id)
        logger.info("Группа %s стала супергруппой %s — настройки перенесены", old_id, new_id)
    except Exception as error:
        logger.warning("MIGRATE %s → %s: %s", old_id, new_id, error)
