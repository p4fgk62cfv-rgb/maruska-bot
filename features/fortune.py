"""
Предсказания: «Мара, предскажи».
"""

from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import fortune

from botcontext import display_name_of, is_addressed

from settings.store import get_value, is_enabled

router = Router(name="fortune")


def is_fortune_request(message: Message) -> bool:
    if not is_enabled(message.chat.id, "fortune"):
        return False

    if not message.text or message.text.startswith("/"):
        return False

    if not fortune.mentions_fortune(message.text):
        return False

    return is_addressed(message)


@router.message(Command("fortune", "predict", "future"))
async def fortune_command(message: Message):
    if not is_enabled(message.chat.id, "fortune"):
        await message.reply("🔮 Предсказания в этой группе выключены (/settings).")
        return

    await send_fortune(message)


@router.message(is_fortune_request)
async def fortune_handler(message: Message):
    await send_fortune(message)


def fortune_keyboard(user_id: int, chat_id: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="🔮 Ещё",
                callback_data=f"fortune:more:{user_id}",
            ),
            InlineKeyboardButton(
                text="❤️ Любовь",
                callback_data=f"fortune:love:{user_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                text="💰 Деньги",
                callback_data=f"fortune:money:{user_id}",
            ),
        ],
    ]

    if is_enabled(chat_id, "fortune_vulgar"):
        rows.append([
            InlineKeyboardButton(
                text="🌶️ Пошлятина",
                callback_data=f"fortune:vulgar:{user_id}",
            )
        ])

    if is_enabled(chat_id, "fortune_sarcasm"):
        rows.append([
            InlineKeyboardButton(
                text="😒 Сарказм",
                callback_data=f"fortune:sarcasm:{user_id}",
            )
        ])

    if is_enabled(chat_id, "fortune_roast"):
        rows.append([
            InlineKeyboardButton(
                text="💀 Разъеби меня",
                callback_data=f"fortune:roast:{user_id}",
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_fortune(message: Message, category: str = "more"):
    user = message.from_user

    if user is None or user.is_bot:
        return

    chat_id = message.chat.id
    mode = get_value(chat_id, "fortune_mode") or "roast"

    await message.reply(
        fortune.predict(
            user.id,
            escape(display_name_of(user)),
            mode=mode,
            category=category,
        ),
        reply_markup=fortune_keyboard(user.id, chat_id),
    )


@router.callback_query(F.data.startswith("fortune:"))
async def fortune_button(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return

    category, owner_raw = parts[1], parts[2]

    if category not in {"more", "love", "money", "vulgar", "roast", "sarcasm"}:
        await callback.answer("Неизвестный режим", show_alert=True)
        return

    try:
        owner_id = int(owner_raw)
    except ValueError:
        await callback.answer("Ошибка кнопки", show_alert=True)
        return

    if callback.from_user.id != owner_id:
        await callback.answer("😏 Это предсказание не для тебя.", show_alert=True)
        return

    chat = callback.message.chat if callback.message else None
    if chat is None:
        await callback.answer()
        return

    if category == "vulgar" and not is_enabled(chat.id, "fortune_vulgar"):
        await callback.answer("🌶️ Этот режим выключен администратором.", show_alert=True)
        return

    if category == "sarcasm" and not is_enabled(chat.id, "fortune_sarcasm"):
        await callback.answer("😒 Этот режим выключен администратором.", show_alert=True)
        return

    if category == "roast" and not is_enabled(chat.id, "fortune_roast"):
        await callback.answer("💀 Этот режим выключен администратором.", show_alert=True)
        return

    if not is_enabled(chat.id, "fortune"):
        await callback.answer("🔮 Предсказания выключены.", show_alert=True)
        return

    mode = get_value(chat.id, "fortune_mode") or "roast"
    user = callback.from_user

    if category == "roast" and is_enabled(chat.id, "fortune_brutal"):
        mode = "brutal"

    await callback.message.edit_text(
        fortune.predict(
            user.id,
            escape(display_name_of(user)),
            mode=mode,
            category=category,
        ),
        reply_markup=fortune_keyboard(user.id, chat.id),
    )
    await callback.answer()
