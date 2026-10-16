"""
«Мара, нарисуй …» — Маруська рисует картинку и присылает в чат.

Срабатывает, когда к ней обращаются (по имени, @, ответом на её
сообщение или в личке) со словом «нарисуй» в начале, и по командам
/нарисуй и /draw. Лимит картинок в сутки на группу — в настройках.
"""

import asyncio
import logging
import re
import time
from html import escape

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, Message

from botcontext import TRIGGER_RE, is_addressed
from settings.store import get_number, get_value, is_blocked, is_enabled


logger = logging.getLogger("maruska.draw")

router = Router(name="draw")

VERBS = r"(?:нарисуй(?:-ка)?|нарисуешь|нарисовать|порисуй|рисуй|изобрази|сгенерируй|сгенери|сделай\s+(?:картинку|рисунок|арт)|картинку)"
DRAW_RE = re.compile(r"^[\s,.!:—-]*" + VERBS + r"\b[\s,:—-]*(.*)$", re.IGNORECASE | re.DOTALL)

USER_PAUSE = 30          # секунд между рисунками одного человека
_daily: dict[int, tuple[str, int]] = {}
_user_last: dict[tuple[int, int], float] = {}


def strip_address(text: str) -> str:
    """«Мара, нарисуй кота» → «нарисуй кота»: убираем обращение и @бота в начале."""
    text = re.sub(r"^\s*@\w+[\s,]*", "", text)
    match = TRIGGER_RE.match(text.lstrip())
    if match:
        text = text.lstrip()[match.end():]
    return text


def draw_request(message: Message) -> str | None:
    """Что нарисовать, или None — если это не просьба нарисовать."""
    text = message.text or ""
    if not text or text.startswith("/") or not is_addressed(message):
        return None
    match = DRAW_RE.match(strip_address(text))
    if not match:
        return None
    return match.group(1).strip()


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def limit_problem(chat_id: int, user_id: int) -> str | None:
    limit = get_number(chat_id, "draw_daily_limit") or 0
    day, used = _daily.get(chat_id, ("", 0))
    if limit and day == _today() and used >= limit:
        return f"На сегодня я нарисовала уже {used} картинок — лимит группы. Завтра продолжим 🎨"
    last = _user_last.get((chat_id, user_id))
    if last is not None and time.monotonic() - last < USER_PAUSE:
        return f"Дай кисточке остыть — следующую картинку через {int(USER_PAUSE - (time.monotonic() - last)) + 1} сек 🖌"
    return None


def note(chat_id: int, user_id: int) -> None:
    day, used = _daily.get(chat_id, ("", 0))
    _daily[chat_id] = (_today(), used + 1 if day == _today() else 1)
    _user_last[(chat_id, user_id)] = time.monotonic()


async def _keep_typing(message: Message, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await message.bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_PHOTO)
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=4.5)
        except asyncio.TimeoutError:
            pass


async def make_picture(message: Message, prompt: str) -> None:
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not is_enabled(chat_id, "ai_draw"):
        await message.reply("Рисунки в этой группе выключены 🎨")
        return
    if is_blocked(chat_id, user_id):
        return
    if not prompt:
        await message.reply("Что нарисовать? Напиши, например: <b>Мара, нарисуй кота в шляпе на Луне</b>")
        return
    problem = limit_problem(chat_id, user_id)
    if problem:
        await message.reply(problem)
        return

    from ai import images

    safe = is_enabled(chat_id, "draw_safe")

    # Откровенный запрос отсекаем сразу — без «Рисую…» и без траты лимита
    if safe and images.unsafe_prompt(prompt):
        await message.reply("Такое я рисовать не буду 🙈 У нас тут приличный чат — попроси что-нибудь другое")
        return

    enabled = {name for name, on in (
        ("gemini", is_enabled(chat_id, "draw_gemini")),
        ("pollinations", is_enabled(chat_id, "draw_pollinations")),
        ("huggingface", is_enabled(chat_id, "draw_huggingface")),
    ) if on}
    if not enabled:
        await message.reply("Все художники выключены в админке 🎨 Включи хотя бы одного: Маруська → Рисунки")
        return

    note(chat_id, user_id)
    prompt = prompt[:700]
    wait = await message.reply(f"🎨 Рисую «{escape(prompt[:80])}{'…' if len(prompt) > 80 else ''}»…")
    stop = asyncio.Event()
    typing = asyncio.create_task(_keep_typing(message, stop))

    try:
        data, who = await images.draw(prompt, primary=get_value(chat_id, "draw_primary") or "pollinations",
                                      enabled=enabled, safe=safe)
    except images.DrawRefused as error:
        logger.info("DRAW REFUSED: %s", error)
        await _edit(wait, "Получилось неприлично — такое не покажу 🙈 Попробуй сформулировать иначе")
        return
    except images.NoArtist as error:
        logger.warning("DRAW: %s", error)
        await _edit(wait, "Сейчас все мои художники заняты 😔 Попробуй через пару минут")
        return
    except Exception as error:
        logger.error("DRAW ERROR: %s %s", type(error).__name__, error)
        await _edit(wait, "Кисточка сломалась 😔 Попробуй ещё раз чуть позже")
        return
    finally:
        stop.set()
        typing.cancel()

    try:
        await message.reply_photo(
            BufferedInputFile(data, filename="mara.png"),
            caption=f"🎨 {escape(prompt[:900])}",
        )
    except Exception as error:
        logger.error("DRAW SEND: %s %s", type(error).__name__, error)
        await _edit(wait, "Нарисовала, но Telegram не принял картинку 😔 Попробуй ещё раз")
        return

    try:
        await wait.delete()
    except Exception:
        pass

    logger.info("DRAW: %s нарисовал(а) в чате %s", who, chat_id)

    import audit

    audit.count(chat_id, "ai_requests")


async def _edit(wait: Message, text: str) -> None:
    try:
        await wait.edit_text(text)
    except Exception:
        pass


@router.message(Command("draw", "нарисуй", "рисуй"))
async def draw_command(message: Message, command: CommandObject):
    if not message.from_user or message.from_user.is_bot:
        return
    await make_picture(message, (command.args or "").strip())


@router.message(F.text, lambda message: draw_request(message) is not None)
async def draw_by_name(message: Message):
    if not message.from_user or message.from_user.is_bot:
        return
    await make_picture(message, draw_request(message) or "")
