"""
Игры в группе: Мара по расписанию рассказывает, во что можно играть, —
Арена (Дурак онлайн), Рыбалка и игры прямо в чате — с кнопками
«Арена» и «Рыбалка».

Включается в настройках группы («Игры в группе»). Расписание — по
времени группы: от часа «первый раз в» каждые N часов (по умолчанию
каждые 4), в случайную минуту часа; ночью (с 0 до 9) не пишет. Каждый
слот отправляется один раз: отметка в базе (chat_once), поэтому
перезапуск бота посреди часа не даёт повтора.

То же сообщение по команде: /arena, /арена или «арена» отдельным сообщением.
"""

import asyncio
import hashlib
import logging
import random
import time

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from settings.store import get_number, is_enabled, local_now


logger = logging.getLogger("maruska.arena_promo")

router = Router(name="arena_promo")

OPEN_WORDS = {"арена", "мара арена", "мара, арена", "🃏 арена"}
# По команде — не чаще раза в минуту в группе, чтобы не заспамили
COMMAND_COOLDOWN = 60
_last_command: dict[int, float] = {}

CHECK_INTERVAL = 300
NIGHT = range(0, 9)
DEFAULT_EVERY = 4
DEFAULT_START = 10

TEXTS = (
    "🎮 <b>Во что поиграть в чате</b>\n\n"
    "🃏 <b>Арена — Дурак онлайн</b>\n"
    "Подкидной и переводной, от 2 до 6 игроков. Соперники из чата или боты, "
    "турниры каждый день с призами, задания и бонус за вход.\n\n"
    "🎣 <b>Рыбалка</b>\n"
    "Выбирай водоём, забрасывай, вываживай и собирай коллекцию. "
    "Алмазы и опыт — общие с Марой, крупный улов я объявлю в чате.\n\n"
    "🎨 А ещё прямо здесь: «крокодил», /игры — крестики-нолики, морской бой, "
    "камень-ножницы-бумага, /dice — кубики.\n\n"
    "Выбирай 👇",

    "🎲 <b>Скучно? Поиграем!</b>\n\n"
    "🃏 <b>Арена</b> — дурак онлайн прямо в Telegram: садись за стол с ребятами из чата "
    "или против ботов. Сезоны, рейтинг, призы в турнирах.\n\n"
    "🎣 <b>Рыбалка</b> — спокойная игра на удачу и сноровку: редкие рыбы, рекорды "
    "и топ рыбаков группы (/fishtop).\n\n"
    "В чате ещё есть «крокодил» и /игры.\n\n"
    "Жми кнопку 👇",

    "🃏🎣 <b>Игры Мары</b>\n\n"
    "• <b>Арена</b> — дурак: подкидной и переводной, ежедневные и субботние турниры, "
    "позови друга — бонус вам обоим\n"
    "• <b>Рыбалка</b> — водоёмы, снасти, коллекция рыб и рекорды группы\n"
    "• <b>В чате</b> — «крокодил», /игры, /dice, /coin\n\n"
    "Всё без скачивания — открывается в Telegram 👇",
)


def slot_now(hour: int, start: int, every: int) -> bool:
    """Пора ли в этот час: от start каждые every часов, но не ночью."""
    if hour in NIGHT:
        return False
    every = max(1, every)
    return (hour - start) % every == 0


def slot_minute(chat_id: int, day: str, hour: int) -> int:
    """Случайная, но постоянная для слота минута (0–49): после перезапуска та же."""
    digest = hashlib.sha256(f"{chat_id}:{day}:{hour}".encode()).digest()
    return digest[0] % 50


async def games_buttons(bot, chat_id: int, group: bool) -> list[InlineKeyboardButton]:
    """Кнопки «Арена» и «Рыбалка» — те, что сейчас доступны в этом чате."""
    from fishing import service as fs
    from games.arena import play_button
    from games.fishing import fishing_button
    from settings import store
    from webapp.server import public_url

    me = await bot.me()
    username = me.username or ""
    buttons = []

    arena = play_button(username, group)
    if arena is not None:
        buttons.append(arena.model_copy(update={"text": "🃏 Арена — дурак онлайн"}))

    base = public_url()
    if base and fs.settings()["enabled"] and not (group and not store.is_enabled(chat_id, "fishing")):
        buttons.append(fishing_button(username, chat_id, group, base, text="🎣 Рыбалка"))

    return buttons


async def send_promo(bot, chat_id: int, group: bool = True) -> bool:
    buttons = await games_buttons(bot, chat_id, group)
    if not buttons:
        return False
    await bot.send_message(
        chat_id,
        random.choice(TEXTS),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[b] for b in buttons]),
    )
    return True


def is_open_request(message: Message) -> bool:
    return message.reply_to_message is None and (message.text or "").strip().lower() in OPEN_WORDS


@router.message(Command("arena", "арена", ignore_case=True))
@router.message(is_open_request)
async def arena_promo_command(message: Message):
    now = time.monotonic()
    if now - _last_command.get(message.chat.id, float("-inf")) < COMMAND_COOLDOWN:
        return
    _last_command[message.chat.id] = now
    if not await send_promo(message.bot, message.chat.id, group=message.chat.type != "private"):
        _last_command.pop(message.chat.id, None)
        await message.reply("🎮 Игры скоро откроются — игровой сервер ещё не подключён.")


async def check_chat(bot, chat_id: int) -> bool:
    """Одна проверка группы: шлёт сообщение, если сейчас слот и он ещё не отправлен."""
    from database.repository import mark_chat_once

    if not is_enabled(chat_id, "arena_promo"):
        return False

    here = local_now(chat_id)
    every = get_number(chat_id, "arena_promo_hours") or DEFAULT_EVERY
    start = get_number(chat_id, "arena_promo_hour")
    start = DEFAULT_START if start is None else start
    day = f"{here:%Y-%m-%d}"

    if not slot_now(here.hour, start, every):
        return False

    if here.minute < slot_minute(chat_id, day, here.hour):
        return False

    if not await mark_chat_once(chat_id, f"arena_promo:{day}:{here.hour}"):
        return False

    try:
        return await send_promo(bot, chat_id)
    except Exception as error:
        logger.warning("ARENA PROMO %s: %s %s", chat_id, type(error).__name__, error)
        return False


async def arena_promo_loop(bot):
    """Раз в пять минут проверяет живые группы: не пора ли рассказать про игры."""
    from database.repository import get_active_chats, get_group_settings
    from settings.store import is_loaded, prime

    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL)
            for chat_id in await get_active_chats(days=30):
                if not is_loaded(chat_id):
                    try:
                        prime(chat_id, await get_group_settings(chat_id))
                    except Exception:
                        prime(chat_id, {})
                if await check_chat(bot, chat_id):
                    logger.info("ARENA PROMO: отправила в %s", chat_id)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.error("ARENA PROMO LOOP: %s %s", type(error).__name__, error)
