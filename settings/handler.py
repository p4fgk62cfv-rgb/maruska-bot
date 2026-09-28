"""
Админ-панель: /settings

Переключатели, списки и числа строятся из реестра автоматически —
новая настройка появляется в панели сама, без правок этого файла.

Доступ: администраторы группы управляют своей группой, владельцы
бота из OWNER_IDS — любой.

Панель разбита на разделы: настроек стало больше двадцати, и одним
экраном они уже не помещаются.
"""

import logging
import os
import re
import time
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
from settings.registry import (
    CHOICE_BY_KEY,
    CHOICES,
    FEATURE_BY_KEY,
    FEATURES,
    NUMBER_BY_KEY,
    NUMBERS,
    TEXT_BY_KEY,
    TEXTS,
    by_group,
    choices_by_group,
    groups,
    numbers_by_group,
    option_label,
    texts_by_group,
)


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


# OWNER_IDS — владельцы бота. Могут менять настройки в любой группе,
# даже не будучи там администраторами.
#
# Администраторы группы при этом ВСЕГДА управляют своей группой:
# бота добавили к ним, им и решать, что в нём включено.
OWNER_IDS = _parse_owners(os.getenv("OWNER_IDS", ""))

# Главные админы бота: их назначает создатель в панели («Ещё → Главные админы»),
# права у них те же, что у OWNER_IDS. Список живёт в таблице bot_owners
# и держится здесь в памяти — is_owner вызывается на каждое сообщение.
_GRANTED: frozenset[int] = frozenset()


def set_granted_owners(ids) -> None:
    global _GRANTED
    _GRANTED = frozenset(int(i) for i in ids)


def granted_owners() -> frozenset[int]:
    return _GRANTED


def is_creator(user_id: int | None) -> bool:
    """Создатель — из OWNER_IDS. Только он назначает и снимает главных админов."""
    return bool(user_id) and user_id in OWNER_IDS


def is_owner(user_id: int | None) -> bool:
    """Полные права во всём боте: создатель или назначенный им главный админ."""
    return bool(user_id) and (user_id in OWNER_IDS or user_id in _GRANTED)


async def is_admin(event, bot) -> bool:
    if isinstance(event, CallbackQuery):
        chat = event.message.chat if event.message else None
        user = event.from_user
    else:
        chat = event.chat
        user = event.from_user

    if is_owner(user.id if user else None):
        return True

    if chat is None:
        return False

    if chat.type not in GROUP_CHATS:
        return True

    try:
        member = await bot.get_chat_member(chat.id, user.id)
    except Exception as error:
        logger.warning("ADMIN CHECK: %s", error)
        return False

    return member.status in ADMIN_STATUSES


# ---------------------------------------------------------
# Главный экран: разделы
# ---------------------------------------------------------

def _section_id(name: str) -> str:
    return str(groups().index(name))


def _section_name(section: str) -> str | None:
    names = groups()

    try:
        return names[int(section)]
    except (ValueError, IndexError):
        return None


def _section_summary(chat_id: int, name: str) -> str:
    values = store.values(chat_id)

    features = by_group(name)

    on = sum(
        1
        for feature in features
        if values.get(feature.key, feature.default)
    )

    extra = (
        len(choices_by_group(name))
        + len(numbers_by_group(name))
        + len(texts_by_group(name))
    )

    parts = []

    if features:
        parts.append(f"{on}/{len(features)}")

    if extra:
        parts.append(f"+{extra}")

    return " ".join(parts)


# Короткое имя Mini App с панелью (BotFather -> /newapp)
WEBAPP_ADMIN_NAME = os.getenv("WEBAPP_ADMIN_NAME", "").strip()

BOT_USERNAME = ""


def set_bot_username(username: str) -> None:
    global BOT_USERNAME

    BOT_USERNAME = username or ""


def admin_url() -> str:
    if not (WEBAPP_ADMIN_NAME and BOT_USERNAME):
        return ""

    return f"https://t.me/{BOT_USERNAME}/{WEBAPP_ADMIN_NAME}"


def main_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    rows = []

    url = admin_url()

    if url:
        rows.append([
            InlineKeyboardButton(text="🖥 Веб-панель", url=url),
        ])
    else:
        rows.append([
            InlineKeyboardButton(
                text="🖥 Веб-панель недоступна",
                callback_data="set:noop",
            ),
        ])

    rows.append([
        InlineKeyboardButton(text="Закрыть", callback_data="set:close"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def panel_text(chat_title: str | None) -> str:
    where = f" — <b>{escape(chat_title)}</b>" if chat_title else ""

    return (
        f"⚙️ <b>Настройки</b>{where}\n\n"
        "Все настройки группы доступны в Web-панели.\n"
        "Открой её для полного управления Маруськой."
    )


# ---------------------------------------------------------
# Экран раздела
# ---------------------------------------------------------

def section_keyboard(chat_id: int, name: str) -> InlineKeyboardMarkup:
    values = store.values(chat_id)
    rows = []

    for feature in by_group(name):
        enabled = values.get(feature.key, feature.default)
        mark = "✅" if enabled else "❌"

        rows.append([
            InlineKeyboardButton(
                text=f"{mark} {feature.emoji} {feature.title}",
                callback_data=f"set:toggle:{feature.key}",
            )
        ])

    for choice in choices_by_group(name):
        current = values.get(choice.key, choice.default)

        rows.append([
            InlineKeyboardButton(
                text=(
                    f"{choice.emoji} {choice.title}: "
                    f"{option_label(choice.key, current)}"
                ),
                callback_data=f"set:pick:{choice.key}",
            )
        ])

    for number in numbers_by_group(name):
        current = store.get_number(chat_id, number.key)

        rows.append([
            InlineKeyboardButton(
                text=f"{number.emoji} {number.title}: {number.label(current)}",
                callback_data=f"set:num:{number.key}",
            )
        ])

    for text in texts_by_group(name):
        current = store.get_text(chat_id, text.key)
        changed = "✏️" if current != text.default else ""

        rows.append([
            InlineKeyboardButton(
                text=f"{text.emoji} {text.title} {changed}".strip(),
                callback_data=f"set:txt:{text.key}",
            )
        ])

    rows.append([
        InlineKeyboardButton(text="← Разделы", callback_data="set:home"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def section_text(name: str) -> str:
    return f"⚙️ <b>{name}</b>\n\nТапни, чтобы переключить или изменить."


# ---------------------------------------------------------
# Экран выбора из списка
# ---------------------------------------------------------

def options_keyboard(chat_id: int, key: str) -> InlineKeyboardMarkup:
    choice = CHOICE_BY_KEY[key]
    current = store.values(chat_id).get(choice.key, choice.default)

    rows = []

    for value, label, emoji in choice.options:
        mark = "🔘" if value == current else "⚪"

        rows.append([
            InlineKeyboardButton(
                text=f"{mark} {emoji} {label}",
                callback_data=f"set:set:{key}:{value}",
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="← Назад",
            callback_data=f"set:sec:{_section_id(choice.group)}",
        ),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------------------------------------------------------
# Экран числа
# ---------------------------------------------------------

def number_keyboard(chat_id: int, key: str) -> InlineKeyboardMarkup:
    number = NUMBER_BY_KEY[key]

    big = number.step * 5

    rows = [
        [
            InlineKeyboardButton(
                text=f"−{big}",
                callback_data=f"set:add:{key}:{-big}",
            ),
            InlineKeyboardButton(
                text=f"−{number.step}",
                callback_data=f"set:add:{key}:{-number.step}",
            ),
            InlineKeyboardButton(
                text=f"+{number.step}",
                callback_data=f"set:add:{key}:{number.step}",
            ),
            InlineKeyboardButton(
                text=f"+{big}",
                callback_data=f"set:add:{key}:{big}",
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"Мин ({number.label(number.minimum)})",
                callback_data=f"set:put:{key}:{number.minimum}",
            ),
            InlineKeyboardButton(
                text=f"Макс ({number.label(number.maximum)})",
                callback_data=f"set:put:{key}:{number.maximum}",
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"↺ Сбросить ({number.label(number.resolve_default())})",
                callback_data=f"set:put:{key}:{number.resolve_default()}",
            ),
        ],
        [
            InlineKeyboardButton(
                text="← Назад",
                callback_data=f"set:sec:{_section_id(number.group)}",
            ),
        ],
    ]

    return InlineKeyboardMarkup(inline_keyboard=rows)


def number_text(chat_id: int, key: str) -> str:
    number = NUMBER_BY_KEY[key]
    current = store.get_number(chat_id, key)

    return (
        f"{number.emoji} <b>{number.title}</b>\n\n"
        f"{number.description}\n\n"
        f"Сейчас: <b>{number.label(current)}</b>\n"
        f"<i>Допустимо от {number.minimum} до {number.maximum}</i>"
    )


# ---------------------------------------------------------
# Экран текста
# ---------------------------------------------------------
#
# Текст кнопками не наберёшь, поэтому бот просит прислать его
# сообщением. Кто и что именно правит — в _pending, с коротким
# сроком жизни, чтобы забытая правка не перехватывала чужие
# сообщения через час.
#
# ---------------------------------------------------------

PENDING_TTL = 300      # секунд на ввод

# (chat_id, user_id) -> (ключ, когда попросили)
_pending: dict[tuple[int, int], tuple[str, float]] = {}

PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")


def _remember_pending(chat_id: int, user_id: int, key: str) -> None:
    _pending[(chat_id, user_id)] = (key, time.monotonic())


def _take_pending(chat_id: int, user_id: int) -> str | None:
    found = _pending.get((chat_id, user_id))

    if found is None:
        return None

    key, asked_at = found

    if time.monotonic() - asked_at > PENDING_TTL:
        _pending.pop((chat_id, user_id), None)
        return None

    return key


def _forget_pending(chat_id: int, user_id: int) -> None:
    _pending.pop((chat_id, user_id), None)


def text_keyboard(chat_id: int, key: str) -> InlineKeyboardMarkup:
    text = TEXT_BY_KEY[key]
    own = store.get_text(chat_id, key) != text.default

    rows = [[
        InlineKeyboardButton(
            text="✏️ Изменить",
            callback_data=f"set:edit:{key}",
        ),
    ]]

    if own:
        rows.append([
            InlineKeyboardButton(
                text="↺ Вернуть стандартный",
                callback_data=f"set:reset:{key}",
            ),
        ])

    rows.append([
        InlineKeyboardButton(
            text="← Назад",
            callback_data=f"set:sec:{_section_id(text.group)}",
        ),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def text_screen(chat_id: int, key: str) -> str:
    text = TEXT_BY_KEY[key]
    current = store.get_text(chat_id, key)
    own = current != text.default

    lines = [
        f"{text.emoji} <b>{text.title}</b>",
        "",
        text.description,
        "",
        f"<b>Сейчас{' (свой)' if own else ' (стандартный)'}:</b>",
        "",
        f"<code>{escape(current)}</code>",
    ]

    hint = text.hint()

    if hint:
        lines.append("")
        lines.append(hint)

    return "\n".join(lines)


def _validate_text(text, value: str) -> str | None:
    """
    Возвращает сообщение об ошибке или None, если всё хорошо.
    """
    if not value.strip() and not text.allow_empty:
        return "Пустой текст не подойдёт."

    if len(value) > text.max_length:
        return (
            f"Слишком длинно: {len(value)} символов, "
            f"максимум {text.max_length}."
        )

    unknown = set(PLACEHOLDER_RE.findall(value)) - set(text.placeholders)

    if unknown:
        allowed = ", ".join(f"{{{p}}}" for p in text.placeholders) or "никакие"

        return (
            "Непонятные подстановки: "
            + ", ".join(f"{{{name}}}" for name in sorted(unknown))
            + f".\nРазрешены: {allowed}."
        )

    return None


@router.callback_query(F.data.startswith("set:txt:"))
async def open_text(callback: CallbackQuery, bot):
    if not await is_admin(callback, bot):
        await callback.answer(DENIED, show_alert=True)
        return

    key = callback.data.split(":", 2)[2]

    if key not in TEXT_BY_KEY:
        await callback.answer("Неизвестная настройка", show_alert=True)
        return

    chat_id = callback.message.chat.id

    await callback.message.edit_text(
        text_screen(chat_id, key),
        reply_markup=text_keyboard(chat_id, key),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("set:edit:"))
async def ask_text(callback: CallbackQuery, bot):
    if not await is_admin(callback, bot):
        await callback.answer(DENIED, show_alert=True)
        return

    key = callback.data.split(":", 2)[2]
    text = TEXT_BY_KEY.get(key)

    if text is None:
        await callback.answer("Неизвестная настройка", show_alert=True)
        return

    chat = callback.message.chat

    _remember_pending(chat.id, callback.from_user.id, key)

    hint = text.hint()

    await callback.message.answer(
        f"✏️ Пришли новый текст для «{text.title}».\n\n"
        + (f"{hint}\n" if hint else "")
        + f"Не больше {text.max_length} символов. "
        "Можно использовать <b>жирный</b> и <i>курсив</i>.\n\n"
        "Чтобы отменить — напиши <code>отмена</code>."
    )

    await callback.answer("Жду текст сообщением")


@router.callback_query(F.data.startswith("set:reset:"))
async def reset_text(callback: CallbackQuery, bot):
    if not await is_admin(callback, bot):
        await callback.answer(DENIED, show_alert=True)
        return

    key = callback.data.split(":", 2)[2]
    text = TEXT_BY_KEY.get(key)

    if text is None:
        await callback.answer("Неизвестная настройка", show_alert=True)
        return

    if not await store_value(callback, key, text.default):
        return

    chat_id = callback.message.chat.id

    await callback.message.edit_text(
        text_screen(chat_id, key),
        reply_markup=text_keyboard(chat_id, key),
    )

    await callback.answer("Вернула стандартный")


def is_text_input(message: Message) -> bool:
    """
    Ловим только сообщение от того, кто минуту назад нажал
    «Изменить». Всё остальное идёт дальше как обычно.
    """
    if not message.text or not message.from_user:
        return False

    return _take_pending(message.chat.id, message.from_user.id) is not None


@router.message(is_text_input)
async def receive_text(message: Message):
    key = _take_pending(message.chat.id, message.from_user.id)

    if key is None:
        return

    text = TEXT_BY_KEY.get(key)

    if text is None:
        _forget_pending(message.chat.id, message.from_user.id)
        return

    value = message.html_text or message.text

    if value.strip().lower() in ("отмена", "cancel", "/cancel"):
        _forget_pending(message.chat.id, message.from_user.id)
        await message.reply("Отменила, текст остался прежним.")
        return

    problem = _validate_text(text, value)

    if problem:
        await message.reply(f"⚠️ {problem}\n\nПопробуй ещё раз.")
        # Ожидание оставляем: человек просто пришлёт другой вариант
        _remember_pending(message.chat.id, message.from_user.id, key)
        return

    _forget_pending(message.chat.id, message.from_user.id)

    store.apply(message.chat.id, key, value)

    try:
        await set_group_setting(
            chat_id=message.chat.id,
            key=key,
            value=value,
            title=message.chat.title,
        )
    except Exception as error:
        logger.error("TEXT SAVE: %s %s", type(error).__name__, error)
        await message.reply("Не сохранилось, попробуй ещё раз.")
        return

    preview = value

    if text.placeholders:
        preview = value.replace(
            "{name}",
            escape(
                message.from_user.first_name
                or message.from_user.username
                or "Новичок"
            ),
        )

    await message.reply(
        f"✅ Готово. Вот как это будет выглядеть:\n\n{preview}"
    )


# ---------------------------------------------------------
# Справка
# ---------------------------------------------------------

def help_text() -> str:
    lines = ["❔ <b>Что настраивается</b>"]

    for name in groups():
        lines.append(f"\n<b>{name}</b>")

        for feature in by_group(name):
            lines.append(
                f"{feature.emoji} <b>{feature.title}</b> — "
                f"{feature.description}"
            )

        for choice in choices_by_group(name):
            lines.append(
                f"{choice.emoji} <b>{choice.title}</b> — "
                f"{choice.description}"
            )

        for number in numbers_by_group(name):
            lines.append(
                f"{number.emoji} <b>{number.title}</b> — "
                f"{number.description}"
            )

        for text in texts_by_group(name):
            lines.append(
                f"{text.emoji} <b>{text.title}</b> — {text.description}"
            )

    return "\n".join(lines)


# ---------------------------------------------------------
# Сохранение
# ---------------------------------------------------------

async def store_value(callback: CallbackQuery, key: str, value) -> bool:
    """
    Пишет значение в кэш и базу. При неудаче откатывает кэш,
    чтобы панель не показывала то, чего нет в базе.
    """
    chat = callback.message.chat
    previous = store.values(chat.id).get(key)

    store.apply(chat.id, key, value)

    try:
        await set_group_setting(
            chat_id=chat.id,
            key=key,
            value=value,
            title=chat.title,
        )
        return True
    except Exception as error:
        logger.error("SETTINGS SAVE: %s %s", type(error).__name__, error)

        if previous is not None:
            store.apply(chat.id, key, previous)

        await callback.answer(
            "Не сохранилось, попробуй ещё раз",
            show_alert=True,
        )
        return False


# ---------------------------------------------------------
# Команды
# ---------------------------------------------------------

@router.message(Command("settings"))
async def show_settings(message: Message, bot):
    if message.chat.type not in GROUP_CHATS:
        await message.answer(
            "⚙️ Настройки задаются для группы. "
            "Добавь меня в чат и напиши /settings там."
        )
        return

    if not await is_admin(message, bot):
        await message.reply("⚙️ Настройки доступны администраторам группы.")
        return

    await message.answer(
        panel_text(message.chat.title),
        reply_markup=main_keyboard(message.chat.id),
    )


@router.message(Command("features"))
async def list_features(message: Message):
    """
    Быстрый способ увидеть всё сразу, без кнопок.
    """
    if message.chat.type not in GROUP_CHATS:
        await message.answer(help_text())
        return

    chat_id = message.chat.id
    values = store.values(chat_id)

    lines = ["⚙️ <b>Сейчас в этой группе</b>"]

    for name in groups():
        lines.append(f"\n<b>{name}</b>")

        for feature in by_group(name):
            mark = "✅" if values.get(feature.key, feature.default) else "❌"
            lines.append(f"{mark} {feature.emoji} {feature.title}")

        for choice in choices_by_group(name):
            current = values.get(choice.key, choice.default)
            lines.append(
                f"{choice.emoji} {choice.title}: "
                f"{option_label(choice.key, current)}"
            )

        for number in numbers_by_group(name):
            current = store.get_number(chat_id, number.key)
            lines.append(
                f"{number.emoji} {number.title}: {number.label(current)}"
            )

        for text in texts_by_group(name):
            own = store.get_text(chat_id, text.key) != text.default
            lines.append(
                f"{text.emoji} {text.title}: "
                f"{'свой' if own else 'стандартный'}"
            )

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


# ---------------------------------------------------------
# Кнопки
# ---------------------------------------------------------

@router.callback_query(F.data == "set:home")
async def go_home(callback: CallbackQuery):
    await callback.message.edit_text(
        panel_text(callback.message.chat.title),
        reply_markup=main_keyboard(callback.message.chat.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set:sec:"))
async def open_section(callback: CallbackQuery):
    name = _section_name(callback.data.split(":", 2)[2])

    if name is None:
        await callback.answer()
        return

    await callback.message.edit_text(
        section_text(name),
        reply_markup=section_keyboard(callback.message.chat.id, name),
    )

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

    if not await store_value(callback, key, not current):
        return

    try:
        await callback.message.edit_reply_markup(
            reply_markup=section_keyboard(chat.id, feature.group)
        )
    except Exception:
        pass

    await callback.answer(
        f"{feature.title}: {'включено' if not current else 'выключено'}"
    )


@router.callback_query(F.data.startswith("set:pick:"))
async def pick_option(callback: CallbackQuery, bot):
    if not await is_admin(callback, bot):
        await callback.answer(DENIED, show_alert=True)
        return

    key = callback.data.split(":", 2)[2]
    choice = CHOICE_BY_KEY.get(key)

    if choice is None:
        await callback.answer("Неизвестная настройка", show_alert=True)
        return

    await callback.message.edit_text(
        f"{choice.emoji} <b>{choice.title}</b>\n\n{choice.description}",
        reply_markup=options_keyboard(callback.message.chat.id, key),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("set:set:"))
async def set_option(callback: CallbackQuery, bot):
    if not await is_admin(callback, bot):
        await callback.answer(DENIED, show_alert=True)
        return

    parts = callback.data.split(":", 3)

    if len(parts) < 4:
        await callback.answer()
        return

    key, value = parts[2], parts[3]
    choice = CHOICE_BY_KEY.get(key)

    if choice is None or value not in {o[0] for o in choice.options}:
        await callback.answer("Неизвестный вариант", show_alert=True)
        return

    if not await store_value(callback, key, value):
        return

    await callback.message.edit_text(
        section_text(choice.group),
        reply_markup=section_keyboard(callback.message.chat.id, choice.group),
    )

    await callback.answer(f"{choice.title}: {option_label(key, value)}")


@router.callback_query(F.data.startswith("set:num:"))
async def open_number(callback: CallbackQuery, bot):
    if not await is_admin(callback, bot):
        await callback.answer(DENIED, show_alert=True)
        return

    key = callback.data.split(":", 2)[2]

    if key not in NUMBER_BY_KEY:
        await callback.answer("Неизвестная настройка", show_alert=True)
        return

    chat_id = callback.message.chat.id

    await callback.message.edit_text(
        number_text(chat_id, key),
        reply_markup=number_keyboard(chat_id, key),
    )

    await callback.answer()


async def _change_number(callback: CallbackQuery, key: str, value: int):
    number = NUMBER_BY_KEY[key]
    chat_id = callback.message.chat.id

    target = number.clamp(value)
    current = store.get_number(chat_id, key)

    if target == current:
        await callback.answer("Дальше некуда")
        return

    if not await store_value(callback, key, target):
        return

    try:
        await callback.message.edit_text(
            number_text(chat_id, key),
            reply_markup=number_keyboard(chat_id, key),
        )
    except Exception:
        pass

    await callback.answer(f"{number.title}: {number.label(target)}")


@router.callback_query(F.data.startswith("set:add:"))
async def add_number(callback: CallbackQuery, bot):
    if not await is_admin(callback, bot):
        await callback.answer(DENIED, show_alert=True)
        return

    parts = callback.data.split(":", 3)

    if len(parts) < 4 or parts[2] not in NUMBER_BY_KEY:
        await callback.answer()
        return

    key = parts[2]

    try:
        delta = int(parts[3])
    except ValueError:
        await callback.answer()
        return

    current = store.get_number(callback.message.chat.id, key)

    await _change_number(callback, key, current + delta)


@router.callback_query(F.data.startswith("set:put:"))
async def put_number(callback: CallbackQuery, bot):
    if not await is_admin(callback, bot):
        await callback.answer(DENIED, show_alert=True)
        return

    parts = callback.data.split(":", 3)

    if len(parts) < 4 or parts[2] not in NUMBER_BY_KEY:
        await callback.answer()
        return

    try:
        value = int(parts[3])
    except ValueError:
        await callback.answer()
        return

    await _change_number(callback, parts[2], value)


@router.callback_query(F.data == "set:noop")
async def noop(callback: CallbackQuery):
    await callback.answer()
