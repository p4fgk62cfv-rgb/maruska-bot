"""
Магазин и подарки.

/shop         — каталог по категориям
/buy <товар>  — купить себе
/gift <товар> — подарить (реплаем или через @username)
/inventory    — что накопилось
"""

import logging
import re
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.repository import (
    add_inventory_item,
    change_balance,
    get_balance,
    get_inventory,
    get_user_by_username,
    save_user,
)

from economy.service import CURRENCY, money, plural
from economy.shop import (
    CATEGORIES,
    ITEM_BY_KEY,
    Item,
    by_category,
    category_title,
    find,
)

from settings.store import is_enabled


logger = logging.getLogger("maruska.shop")

router = Router(name="shop")

USERNAME_RE = re.compile(r"@([A-Za-z0-9_]{5,32})")


def display_name(user) -> str:
    return user.first_name or user.username or "Игрок"


def shop_on(message: Message) -> bool:
    return is_enabled(message.chat.id, "economy")


# ---------------------------------------------------------
# Каталог
# ---------------------------------------------------------

def categories_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=category_title(key),
                callback_data=f"shop:cat:{key}",
            )
        ]
        for key in CATEGORIES
    ]

    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_keyboard(category: str) -> InlineKeyboardMarkup:
    rows = []

    for item in by_category(category):
        rows.append([
            InlineKeyboardButton(
                text=f"{item.emoji} {item.title} — {item.price} 💎",
                callback_data=f"shop:buy:{item.key}",
            )
        ])

    rows.append([
        InlineKeyboardButton(text="← Категории", callback_data="shop:home"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("shop"))
async def shop_command(message: Message):
    if not shop_on(message):
        await message.reply(f"{CURRENCY} Экономика в этой группе выключена (/settings).")
        return

    balance = await get_balance(message.from_user.id) if message.from_user else 0

    await message.answer(
        f"🛍 <b>Магазин</b>\n\n"
        f"У тебя: <b>{money(balance)}</b>\n\n"
        "Выбери раздел. Купленное попадает в инвентарь и видно "
        "в профиле.\n"
        "Подарить: <code>/gift роза</code> реплаем на сообщение.",
        reply_markup=categories_keyboard(),
    )


@router.callback_query(F.data == "shop:home")
async def shop_home(callback: CallbackQuery):
    await callback.message.edit_text(
        "🛍 <b>Магазин</b>\n\nВыбери раздел:",
        reply_markup=categories_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("shop:cat:"))
async def shop_category(callback: CallbackQuery):
    category = callback.data.split(":", 2)[2]

    if category not in CATEGORIES:
        await callback.answer()
        return

    items = by_category(category)

    lines = [f"{category_title(category)}\n"]

    for item in items:
        note = f" — {item.description}" if item.description else ""
        lines.append(f"{item.emoji} <b>{item.title}</b>, {item.price} 💎{note}")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=category_keyboard(category),
    )

    await callback.answer()


# ---------------------------------------------------------
# Покупка
# ---------------------------------------------------------

async def purchase(
    message_or_callback,
    user,
    item: Item,
    chat_id: int,
) -> tuple[bool, str]:
    """
    Списывает алмазы и кладёт вещь в инвентарь.
    Возвращает (получилось, текст ответа).
    """
    await save_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    ok, balance = await change_balance(
        telegram_id=user.id,
        amount=-item.price,
        reason="purchase",
        note=f"Покупка: {item.title}",
        chat_id=chat_id,
        display_name=display_name(user),
    )

    if not ok:
        need = item.price - balance
        return False, (
            f"Не хватает <b>{need} {plural(need)}</b>.\n"
            f"У тебя {money(balance)}, а {item.title.lower()} стоит "
            f"{item.price} 💎.\n\n/bonus — забрать ежедневный"
        )

    await add_inventory_item(user.id, item.key)

    return True, (
        f"{item.emoji} <b>{item.title}</b> — твой!\n"
        f"Списано {item.price} 💎, осталось <b>{money(balance)}</b>"
    )


@router.callback_query(F.data.startswith("shop:buy:"))
async def buy_callback(callback: CallbackQuery):
    key = callback.data.split(":", 2)[2]
    item = ITEM_BY_KEY.get(key)

    if item is None:
        await callback.answer("Товар не найден", show_alert=True)
        return

    ok, text = await purchase(
        callback,
        callback.from_user,
        item,
        callback.message.chat.id,
    )

    if not ok:
        await callback.answer(
            re.sub(r"<[^>]+>", "", text).strip(),
            show_alert=True,
        )
        return

    await callback.answer(f"Куплено: {item.title}")
    await callback.message.answer(
        f"🛍 <b>{escape(display_name(callback.from_user))}</b> покупает "
        f"{item.emoji} <b>{item.title}</b>"
    )


@router.message(Command("buy"))
async def buy_command(message: Message):
    if not shop_on(message):
        await message.reply(f"{CURRENCY} Экономика в этой группе выключена (/settings).")
        return

    if message.from_user is None:
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) < 2:
        await message.reply(
            "Что купить? Например: <code>/buy роза</code>\n"
            "Весь список — /shop"
        )
        return

    item = find(parts[1])

    if item is None:
        await message.reply("Такого товара нет. Посмотри /shop")
        return

    _ok, text = await purchase(message, message.from_user, item, message.chat.id)

    await message.reply(text)


# ---------------------------------------------------------
# Подарки
# ---------------------------------------------------------

async def resolve_target(message: Message):
    """
    Кому дарим: реплаем или через @username.
    """
    reply = message.reply_to_message

    if reply and reply.from_user and not reply.from_user.is_bot:
        user = reply.from_user
        return user.id, display_name(user)

    match = USERNAME_RE.search(message.text or "")

    if match:
        db_user = await get_user_by_username(match.group(1))

        if db_user is not None:
            return (
                db_user.telegram_id,
                db_user.first_name or db_user.username or "Игрок",
            )

    return None, None


@router.message(Command("gift"))
async def gift_command(message: Message):
    if not shop_on(message):
        await message.reply(f"{CURRENCY} Экономика в этой группе выключена (/settings).")
        return

    user = message.from_user

    if user is None:
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) < 2:
        await message.reply(
            "Кому и что? Ответь на сообщение человека и напиши:\n"
            "<code>/gift роза</code>\n\n"
            "Или укажи ник: <code>/gift роза @username</code>\n"
            "Список товаров — /shop"
        )
        return

    # Из аргументов убираем упоминание, остальное — название товара
    query = USERNAME_RE.sub("", parts[1]).strip()
    item = find(query)

    if item is None:
        await message.reply("Не поняла, что дарим. Список — /shop")
        return

    if not item.giftable:
        await message.reply("Это подарить нельзя.")
        return

    target_id, target_name = await resolve_target(message)

    if target_id is None:
        await message.reply(
            "Не поняла, кому. Ответь на сообщение человека "
            "или укажи @username."
        )
        return

    if target_id == user.id:
        await message.reply("Подарить самому себе — это просто покупка 😏")
        return

    giver_name = display_name(user)

    await save_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    ok, balance = await change_balance(
        telegram_id=user.id,
        amount=-item.price,
        reason="gift_out",
        note=f"Подарок: {item.title} для {target_name}",
        chat_id=message.chat.id,
        display_name=giver_name,
    )

    if not ok:
        need = item.price - balance
        await message.reply(
            f"Не хватает <b>{need} {plural(need)}</b>. "
            f"У тебя {money(balance)}."
        )
        return

    await add_inventory_item(
        telegram_id=target_id,
        item_key=item.key,
        from_telegram_id=user.id,
        from_name=giver_name,
    )

    await message.answer(
        f"🎁 <b>{escape(giver_name)}</b> дарит "
        f"<b>{escape(target_name)}</b> {item.emoji} <b>{item.title}</b>\n\n"
        f"<i>{item.description}</i>"
    )


# ---------------------------------------------------------
# Инвентарь
# ---------------------------------------------------------

def format_inventory(items) -> str:
    if not items:
        return "🎒 Пусто. Загляни в /shop"

    owned = []
    gifted = []

    for row in items:
        item = ITEM_BY_KEY.get(row.item_key)

        if item is None:
            continue

        count = f" ×{row.qty}" if row.qty > 1 else ""

        if row.from_name:
            gifted.append(
                f"{item.emoji} {item.title}{count} "
                f"<i>от {escape(row.from_name)}</i>"
            )
        else:
            owned.append(f"{item.emoji} {item.title}{count}")

    lines = ["🎒 <b>Инвентарь</b>"]

    if gifted:
        lines.append("\n<b>Подарки</b>")
        lines.extend(gifted)

    if owned:
        lines.append("\n<b>Куплено</b>")
        lines.extend(owned)

    return "\n".join(lines)


@router.message(Command("inventory", "inv"))
async def inventory_command(message: Message):
    if not shop_on(message):
        await message.reply(f"{CURRENCY} Экономика в этой группе выключена (/settings).")
        return

    if message.from_user is None:
        return

    items = await get_inventory(message.from_user.id)

    await message.reply(format_inventory(items))
