"""
Арена в группе: Мара по расписанию рассказывает про игру «Арена»
(Дурак онлайн) и даёт кнопку «Войти в игру».

Включается в настройках группы («Арена в группе»). Расписание — по
времени группы: от часа «первый раз в» каждые N часов, ночью (с 0 до 9)
не пишет. Каждый слот отправляется один раз: отметка в базе (chat_once),
поэтому перезапуск бота посреди часа не даёт повтора.

То же сообщение по команде: /arena, /арена или «арена» отдельным сообщением.
"""

import asyncio
import logging
import random
import time

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, Message

from settings.store import get_number, is_enabled, local_now


logger = logging.getLogger("maruska.arena_promo")

router = Router(name="arena_promo")

OPEN_WORDS = {"арена", "мара арена", "мара, арена", "🃏 арена"}
# По команде — не чаще раза в минуту в группе, чтобы не заспамили
COMMAND_COOLDOWN = 60
_last_command: dict[int, float] = {}

CHECK_INTERVAL = 300
NIGHT = range(0, 9)

TEXTS = (
    "🃏 <b>Маруська Арена — Дурак онлайн</b>\n\n"
    "Подкидной и переводной, от 2 до 6 игроков. Играй с людьми из чата или с ботами, "
    "если никого нет.\n\n"
    "🏆 Турниры каждый день с призами\n"
    "🎯 Задания и бонус за каждый день входа\n"
    "🎖 Сезоны с наградами лучшим\n\n"
    "Колоду тасует сервер — карты соперников не видит никто. Заходи 👇",

    "🃏 <b>Кто в дурака?</b>\n\n"
    "В <b>Маруська Арене</b> всегда есть с кем сыграть: подкидной или переводной, "
    "вдвоём или компанией до шести.\n\n"
    "Каждый день — турниры с призовым фондом, задания и подарки за вход. "
    "Собери рамки, рубашки карт и столы в магазине.\n\n"
    "Одна кнопка — и ты за столом 👇",

    "🃏 <b>Арена ждёт!</b>\n\n"
    "Дурак онлайн прямо в Telegram — без скачивания.\n"
    "• живые соперники и боты\n"
    "• ежедневные и субботние турниры\n"
    "• сезонный рейтинг и награды\n"
    "• позови друга — бонус вам обоим\n\n"
    "Жми и садись за стол 👇",
)


def slot_now(hour: int, start: int, every: int) -> bool:
    """Пора ли в этот час: от start каждые every часов, но не ночью."""
    if hour in NIGHT:
        return False
    every = max(1, every)
    return (hour - start) % every == 0


async def send_promo(bot, chat_id: int, group: bool = True) -> bool:
    from games.arena import play_button

    me = await bot.me()
    button = play_button(me.username or "", group=group)
    if button is None:
        return False
    button = button.model_copy(update={"text": "🎮 Войти в игру"})
    await bot.send_message(
        chat_id,
        random.choice(TEXTS),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[button]]),
    )
    return True


def is_open_request(message: Message) -> bool:
    return message.reply_to_message is None and (message.text or "").strip().lower() in OPEN_WORDS


@router.message(Command("arena", "арена", ignore_case=True))
@router.message(is_open_request)
async def arena_promo_command(message: Message):
    now = time.monotonic()
    if now - _last_command.get(message.chat.id, 0) < COMMAND_COOLDOWN:
        return
    _last_command[message.chat.id] = now
    if not await send_promo(message.bot, message.chat.id, group=message.chat.type != "private"):
        _last_command.pop(message.chat.id, None)
        await message.reply("🃏 Арена скоро откроется — игровой сервер ещё не подключён.")


async def check_chat(bot, chat_id: int) -> bool:
    """Одна проверка группы: шлёт сообщение, если сейчас слот и он ещё не отправлен."""
    from database.repository import mark_chat_once

    if not is_enabled(chat_id, "arena_promo"):
        return False

    here = local_now(chat_id)
    every = get_number(chat_id, "arena_promo_hours") or 12
    start = get_number(chat_id, "arena_promo_hour")
    start = 10 if start is None else start

    if not slot_now(here.hour, start, every):
        return False

    if not await mark_chat_once(chat_id, f"arena_promo:{here:%Y-%m-%d}:{here.hour}"):
        return False

    try:
        return await send_promo(bot, chat_id)
    except Exception as error:
        logger.warning("ARENA PROMO %s: %s %s", chat_id, type(error).__name__, error)
        return False


async def arena_promo_loop(bot):
    """Раз в пять минут проверяет живые группы: не пора ли рассказать про Арену."""
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
