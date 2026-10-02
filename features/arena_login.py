"""
Вход в установленное приложение «Арена» (вне Telegram).

Приложение просит у арены заявку и открывает ссылку t.me/<бот>?start=alogin_<id>.
Мара показывает, с какого устройства входят, и кнопку «Войти». Нажатие
подтверждает вход у арены; само приложение заберёт сессию своим секретом —
одной ссылки для входа мало, её можно смело переслать или показать.
"""

import json
import logging
import re
from html import escape

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

logger = logging.getLogger("maruska.arena_login")

router = Router(name="arena_login")

PREFIX = "alogin_"
_ID = re.compile(r"^[A-Za-z0-9]{10,32}$")

EXPIRED = "⌛ Ссылка для входа устарела. Нажмите «Войти через Telegram» в приложении ещё раз."
NOT_CONNECTED = "Арена сейчас недоступна, попробуйте через минуту."


def _request_id(args: str | None) -> str | None:
    if not args or not args.startswith(PREFIX):
        return None
    rid = args[len(PREFIX):]
    return rid if _ID.match(rid) else None


def _is_login(args: str | None) -> bool:
    return _request_id(args) is not None


async def _arena(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    from webapp.arena_admin import _call, arena_secret, arena_url

    if not arena_url() or not arena_secret():
        return 503, {}
    status, text = await _call(method, f"{arena_url()}/api/internal/{path}", body=body)
    try:
        return status, json.loads(text) if text else {}
    except ValueError:
        return status, {}


@router.message(CommandStart(deep_link=True, magic=F.args.func(_is_login)))
async def ask_login(message: Message, command: CommandObject):
    if message.chat.type != "private":
        return
    rid = _request_id(command.args)
    status, info = await _arena("GET", f"app-login/{rid}")
    if status == 503:
        await message.answer(NOT_CONNECTED)
        return
    if status != 200:
        await message.answer(EXPIRED)
        return
    device = info.get("device") or "неизвестное устройство"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Войти в Арену", callback_data=f"alogin:{rid}")]])
    await message.answer(
        "🃏 <b>Вход в Маруська Арену</b>\n\n"
        f"Устройство: {escape(device)}\n\n"
        "Если это вы сейчас входите в приложение — нажмите «Войти». "
        "Если нет — просто не нажимайте: без этого никто не войдёт.",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("alogin:"))
async def confirm_login(callback: CallbackQuery):
    rid = (callback.data or "")[len("alogin:"):]
    if not _ID.match(rid) or callback.message is None or callback.message.chat.type != "private":
        await callback.answer()
        return
    user = callback.from_user
    payload = {
        "id": user.id,
        "first_name": user.first_name or "Игрок",
        **({"last_name": user.last_name} if user.last_name else {}),
        **({"username": user.username} if user.username else {}),
        **({"language_code": user.language_code} if user.language_code else {}),
        "is_premium": bool(user.is_premium),
    }
    status, data = await _arena("POST", f"app-login/{rid}/confirm", {"user": payload})
    if status == 200:
        logger.info("ARENA app login confirmed by %s", user.id)
        await callback.message.edit_text("✅ Вход подтверждён. Вернитесь в приложение «Арена» — игра уже открывается.")
        await callback.answer("Готово")
        return
    if status == 503:
        await callback.answer(NOT_CONNECTED, show_alert=True)
        return
    reason = {
        "BANNED": "⛔ Ваш аккаунт в Арене заблокирован.",
        "FORBIDDEN": "Этот вход уже подтвердил другой аккаунт.",
    }.get(data.get("error", ""), EXPIRED)
    await callback.message.edit_text(reason)
    await callback.answer()
