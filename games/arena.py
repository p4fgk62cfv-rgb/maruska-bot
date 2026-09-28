"""
Маруська Арена — онлайн-дурак как отдельная Telegram Mini App.

  /game, /durak, «игра», «/игра», «дурак», «🎮 играть» — кнопка «🎮 Играть».

Игра живёт в отдельном сервисе (папка arena/, TypeScript): свой сервер,
WebSocket, своя схема «arena» в той же PostgreSQL. Бот только открывает
приложение и (позже) доставляет приглашения и итоги партий.

Telegram не принимает кириллицу в командах меню, поэтому «/игра» ловится
как обычный текст, а в меню бота видна /game.

Настройка:
  ARENA_URL       — публичный адрес сервиса арены (https://…)
  ARENA_APP_NAME  — короткое имя Mini App в BotFather (/newapp → URL = ARENA_URL).
                    Нужно для кнопки в группах и ссылок t.me/<бот>/<имя>?startapp=…
"""

import os

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo


router = Router(name="arena")

# В группах люди пишут «играть» просто в разговоре — там откликаемся только
# на явные фразы, чтобы не засыпать чат кнопками и не перехватывать отгадки крокодила.
OPEN_WORDS = {"/игра", "🎮 играть", "играть в дурака", "го в дурака", "в дурака"}
PRIVATE_WORDS = OPEN_WORDS | {"игра", "играть", "дурак"}


def arena_url() -> str:
    return os.getenv("ARENA_URL", "").strip().rstrip("/")


def arena_app_name() -> str:
    return os.getenv("ARENA_APP_NAME", "").strip()


def play_button(bot_username: str, group: bool) -> InlineKeyboardButton | None:
    """В личке — кнопка web_app, в группе — ссылка на Mini App (web_app там запрещён)."""
    if group:
        name = arena_app_name()
        if not name or not bot_username:
            return None
        return InlineKeyboardButton(text="🎮 Играть", url=f"https://t.me/{bot_username}/{name}")

    url = arena_url()
    if not url:
        return None
    return InlineKeyboardButton(text="🎮 Играть", web_app=WebAppInfo(url=url))


async def open_arena(message: Message):
    group = message.chat.type in ("group", "supergroup")
    me = await message.bot.me()
    button = play_button(me.username or "", group)

    if button is None:
        await message.reply("🎮 Арена скоро откроется — игровой сервер ещё не подключён.")
        return

    await message.answer(
        "🃏 <b>Маруська Арена</b>\n\n"
        "Дурак онлайн с живыми игроками: подкидной и переводной, от 2 до 6 человек.\n"
        "Колоду тасует сервер — карты соперников не видит никто.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[button]]),
    )


@router.message(Command("game", "durak"))
async def arena_command(message: Message):
    await open_arena(message)


def is_open_request(message: Message) -> bool:
    if message.reply_to_message is not None:
        return False
    words = PRIVATE_WORDS if message.chat.type == "private" else OPEN_WORDS
    return (message.text or "").strip().lower() in words


@router.message(is_open_request)
async def arena_text(message: Message):
    await open_arena(message)
