"""
Админ-панель: /settings

Переключатели строятся из реестра автоматически — новая функция
появляется в панели сама, без правок этого файла.

Менять настройки может только администратор группы.
"""

import logging
import os
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.repository import set_group_setting

from settings import store
from settings.registry import FEATURE_BY_KEY, FEATURES, by_group, groups


logger = logging.getLogger("maruska.settings")

router = Router(name="settings")

DENIED = "Настройки не для тебя 🙂"

GROUP_CHATS = ("group", "supergroup")

ADMIN_STATUSES = ("creator", "administrator")


def _parse_owners(raw: str) -> frozenset[int]:
    ids = set()

    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if chunk.lstrip("-").isdigit():
            ids.add(int(chunk))

    return frozenset(ids)


# Если OWNER_IDS задан — настройки доступны только этим людям,
# администраторы групп доступ не получают.
# Пусто — решают администраторы каждой группы.
OWNER_IDS = _parse_owners(os.getenv("OWNER_IDS", ""))


def is_owner(user_id: int | None) -> bool:
    return bool(user_id) and user_id in OWNER_IDS


async def is_admin(message_or_callback, bot) -> bool:
    if isinstance(message_or_callback, CallbackQuery):
        chat = message_or_callback.message.chat
        user = message_or_callback.from_user
    else:
        chat = message_or_callback.chat
        user = message_or_callback.from_user

    # Владелец бота может всё и везде
    if is_owner(user.id if user else None):
        return True

    # Список владельцев задан — больше никого не пускаем
    if OWNER_IDS:
        return False

    if chat.type not in GROUP_CHATS:
        return True

    try:
        member = await bot.get_chat_member(chat.id, user.id)
    except Exception as error:
        logger.warning("ADMIN CHECK: %s", error)
        return False

    return member.status in ADMIN_STATUSES


def build_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    values = store.values(chat_id)
    rows = []

    for name in groups():
        rows.append([
            InlineKeyboardButton(
                text=f"— {name} —",
                callback_data="set:noop",
            )
        ])

        for feature in by_group(name):
            enabled = values.get(feature.key, feature.default)
            mark = "✅" if enabled else "❌"

            rows.append([
                InlineKeyboardButton(
                    text=f"{mark} {feature.emoji} {feature.title}",
                    callback_data=f"set:toggle:{feature.key}",
                )
            ])

    rows.append([
        InlineKeyboardButton(text="❔ Что это", callback_data="set:help"),
        InlineKeyboardButton(text="Закрыть", callback_data="set:close"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def panel_text(chat_title: str | None) -> str:
    where = f" — <b>{escape(chat_title)}</b>" if chat_title else ""

    return (
        f"⚙️ <b>Настройки</b>{where}\n\n"
        "Нажми на функцию, чтобы включить или выключить её "
        "в этой группе.\n"
        "Менять может только администратор."
    )


def help_text() -> str:
    lines = ["❔ <b>Что делают функции</b>\n"]

    for name in groups():
        lines.append(f"\n<b>{name}</b>")
        for feature in by_group(name):
            lines.append(
                f"{feature.emoji} <b>{feature.title}</b> — "
                f"{feature.description}"
            )

    return "\n".join(lines)


@router.message(Command("settings"))
async def show_settings(message: Message, bot):
    if message.chat.type not in GROUP_CHATS:
        await message.answer(
            "⚙️ Настройки задаются для группы. "
            "Добавь меня в чат и напиши /settings там."
        )
        return

    if not await is_admin(message, bot):
        await message.reply(
            "⚙️ Настройки доступны только владельцу бота."
            if OWNER_IDS
            else "⚙️ Настройки доступны администраторам группы."
        )
        return

    await message.answer(
        panel_text(message.chat.title),
        reply_markup=build_keyboard(message.chat.id),
    )


@router.callback_query(F.data == "set:noop")
async def noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data == "set:close")
async def close_panel(callback: CallbackQuery, bot):
    if not await is_admin(callback, bot):
        await callback.answer(DENIED, show_alert=True)
        return

    try:
        await callback.message.delete()
    except Exception:
        await callback.message.edit_text("⚙️ Настройки закрыты.")

    await callback.answer()


@router.callback_query(F.data == "set:help")
async def show_help(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(help_text())


@router.callback_query(F.data.startswith("set:toggle:"))
async def toggle(callback: CallbackQuery, bot):
    if not await is_admin(callback, bot):
        await callback.answer(DENIED, show_alert=True)
        return

    key = callback.data.split(":", 2)[2]
    feature = FEATURE_BY_KEY.get(key)

    if feature is None:
        await callback.answer("Неизвестная настройка", show_alert=True)
        return

    chat = callback.message.chat
    current = store.values(chat.id).get(key, feature.default)
    new_value = not current

    store.apply(chat.id, key, new_value)

    try:
        await set_group_setting(
            chat_id=chat.id,
            key=key,
            value=new_value,
            title=chat.title,
        )
    except Exception as error:
        logger.error("SETTINGS SAVE: %s %s", type(error).__name__, error)
        store.apply(chat.id, key, current)
        await callback.answer("Не сохранилось, попробуй ещё раз", show_alert=True)
        return

    try:
        await callback.message.edit_reply_markup(
            reply_markup=build_keyboard(chat.id)
        )
    except Exception:
        pass

    await callback.answer(
        f"{feature.title}: {'включено' if new_value else 'выключено'}"
    )


@router.message(Command("features"))
async def list_features(message: Message):
    """
    Быстрый способ увидеть, что сейчас включено, без кнопок.
    """
    if message.chat.type not in GROUP_CHATS:
        await message.answer(help_text())
        return

    values = store.values(message.chat.id)
    lines = ["⚙️ <b>Сейчас в этой группе</b>\n"]

    for feature in FEATURES:
        mark = "✅" if values.get(feature.key, feature.default) else "❌"
        lines.append(f"{mark} {feature.emoji} {feature.title}")

    lines.append("\n/settings — изменить")

    await message.answer("\n".join(lines))


@router.message(Command("myid"))
async def my_id(message: Message):
    """
    Нужна, чтобы узнать свой числовой ID для OWNER_IDS.
    """
    user = message.from_user

    if user is None:
        return

    role = "владелец бота" if is_owner(user.id) else "обычный пользователь"

    await message.reply(
        f"🆔 Твой ID: <code>{user.id}</code>\n"
        f"Чат: <code>{message.chat.id}</code>\n\n"
        f"Сейчас ты — {role}."
    )
