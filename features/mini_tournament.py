"""
Мини-турнир группы: запись у Мары, игра в Маруська Арене.

    /старт турнир 5000   — админ группы открывает запись; 5000 — приз в «Дурак Онлайн»
    /стоп турнир         — отменить запись или идущий турнир

Мара публикует сообщение с кнопками «Записаться» и «Передумал» и сразу
дописывает в него каждого, кто записался. На шестом запись закрывается сама,
кнопки пропадают, и Мара передаёт состав Арене. Дальше всё ведёт Арена: сажает
всех за один стол, после каждой партии пишет в группу, кто остался дураком и
выбыл, и даёт ссылку на новый стол — на одного меньше. Победителя поздравляет
в группе, а организатору пишет в личку, кому выдать приз.

Запись хранится в базе (mini_signups): перезапуск бота её не теряет.
"""

import asyncio
import json
import logging
import re
from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from botcontext import display_name_of


logger = logging.getLogger("maruska.mini_tournament")

router = Router(name="mini_tournament")

SEATS = 6
MAX_PRIZE = 1_000_000_000
GROUP_CHATS = ("group", "supergroup")

_locks: dict[int, asyncio.Lock] = {}

NOT_CONNECTED = "🃏 Арена сейчас не подключена — турнир не запустить. Попробуйте позже."


def _lock(chat_id: int) -> asyncio.Lock:
    if chat_id not in _locks:
        _locks[chat_id] = asyncio.Lock()
    return _locks[chat_id]


def credits(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def parse_start(args: str | None) -> tuple[str, int | None] | None:
    """Аргументы «/старт турнир 5000» → ('start', 5000); без суммы — ('start', None). Не «турнир» — None."""
    words = (args or "").lower().replace("ё", "е").split()
    if not words or words[0] not in ("турнир", "турнира"):
        return None
    rest = "".join(words[1:])
    digits = re.sub(r"[^\d]", "", rest)
    return "start", int(digits) if digits else None


def mention(player: dict) -> str:
    return f'<a href="tg://user?id={player["id"]}">{escape(player["name"])}</a>'


def signup_text(prize: int, players: list[dict], closed: bool = False) -> str:
    lines = [f"{i}. {mention(p)}" for i, p in enumerate(players, start=1)]
    lines += [f"{i}. —" for i in range(len(players) + 1, SEATS + 1)]
    head = (
        "🏆 <b>Мини-турнир по дураку!</b>\n"
        "Переводной · подкидывают все · быстрая игра · без ничьей\n\n"
        f"🎁 Призовой фонд: <b>{credits(prize)} кредитов в игре «Дурак Онлайн»</b> — всё забирает победитель.\n"
        "🃏 Играем в Маруська Арене: один стол, после каждой партии дурак выбывает, "
        "пока не останется один. Не зашёл за стол за минуту — техническое поражение.\n\n"
    )
    status = "✅ <b>Стол набран — запись закрыта.</b> Сейчас пришлю ссылку на стол." if closed else (
        f"Участники ({len(players)}/{SEATS}):"
    )
    if closed:
        return head + f"Участники ({len(players)}/{SEATS}):\n" + "\n".join(lines) + "\n\n" + status
    return head + status + "\n" + "\n".join(lines)


def signup_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✋ Записаться", callback_data="mt:join"),
        InlineKeyboardButton(text="🚪 Передумал", callback_data="mt:leave"),
    ]])


async def _arena(method: str, path: str, body: dict | None = None, query: dict | None = None) -> tuple[int, dict]:
    from webapp.arena_admin import _call, arena_secret, arena_url

    if not arena_url() or not arena_secret():
        return 503, {}
    status, text = await _call(method, f"{arena_url()}/api/internal/{path}", body=body, query=query)
    try:
        return status, json.loads(text) if text else {}
    except ValueError:
        return status, {}


async def _organizer(message: Message) -> tuple[int, str] | None:
    """Кто запускает: админ группы (или главный админ бота). Анонимный админ — от имени группы."""
    from settings.handler import is_admin

    if message.sender_chat is not None and message.sender_chat.id == message.chat.id:
        return message.chat.id, message.chat.title or "Админ"
    if message.from_user is None or message.from_user.is_bot:
        return None
    if not await is_admin(message, message.bot):
        return None
    return message.from_user.id, display_name_of(message.from_user)


# ---------------------------------------------------------
# Команды
# ---------------------------------------------------------

@router.message(Command("старт", ignore_case=True), F.chat.type.in_(GROUP_CHATS))
async def start_command(message: Message, command: CommandObject):
    parsed = parse_start(command.args)
    if parsed is None:
        return
    await open_signup(message, parsed[1])


@router.message(Command("турнир", ignore_case=True), F.chat.type.in_(GROUP_CHATS))
async def tournament_command(message: Message, command: CommandObject):
    args = (command.args or "").lower().strip()
    if args.startswith("стоп") or args.startswith("stop") or args.startswith("отмен"):
        await stop_tournament(message)
        return
    await open_signup(message, parse_start(f"турнир {args}")[1])


@router.message(Command("стоп", ignore_case=True), F.chat.type.in_(GROUP_CHATS))
async def stop_command(message: Message, command: CommandObject):
    if parse_start(command.args) is None:
        return
    await stop_tournament(message)


async def open_signup(message: Message, prize: int | None) -> None:
    from database.repository import get_mini_signup, save_mini_signup

    organizer = await _organizer(message)
    if organizer is None:
        await message.reply("🏆 Запускать турнир могут только админы группы.")
        return
    if prize is None:
        await message.reply("🏆 Укажи призовой фонд: <code>/старт турнир 5000</code> — кредиты в «Дурак Онлайн» победителю.")
        return
    if prize > MAX_PRIZE:
        await message.reply("🏆 Слишком большой приз — проверь число.")
        return

    chat_id = message.chat.id
    async with _lock(chat_id):
        if await get_mini_signup(chat_id):
            await message.reply("🏆 Запись на турнир уже идёт — смотри сообщение выше. Отменить: /стоп турнир")
            return
        status, running = await _arena("GET", "mini-tournaments/active", query={"chatId": str(chat_id)})
        if status == 503:
            await message.reply(NOT_CONNECTED)
            return
        if status == 200 and running.get("tournament"):
            await message.reply("🏆 В группе уже идёт мини-турнир. Отменить: /стоп турнир")
            return

        sent = await message.answer(signup_text(prize, []), reply_markup=signup_keyboard())
        await save_mini_signup(
            chat_id, message_id=sent.message_id, prize=prize,
            organizer_id=organizer[0], organizer_name=organizer[1][:128], players=[],
        )
    logger.info("MINI TOURNAMENT: запись открыта в %s, приз %s", chat_id, prize)


async def stop_tournament(message: Message) -> None:
    from database.repository import delete_mini_signup, get_mini_signup

    if await _organizer(message) is None:
        await message.reply("🏆 Отменить турнир могут только админы группы.")
        return
    chat_id = message.chat.id
    async with _lock(chat_id):
        signup = await get_mini_signup(chat_id)
        if signup is not None:
            await delete_mini_signup(chat_id)
            try:
                await message.bot.edit_message_text(
                    "🛑 <b>Мини-турнир отменён.</b> Запись закрыта.", chat_id=chat_id, message_id=signup.message_id,
                )
            except Exception:
                pass
            await message.reply("🛑 Запись на турнир отменена.")
            return
    status, answer = await _arena("POST", "mini-tournaments/cancel", body={"chatId": str(chat_id)})
    if status == 503:
        await message.reply(NOT_CONNECTED)
    elif not answer.get("cancelled"):
        await message.reply("🏆 Сейчас в группе нет турнира.")
    # Об отмене идущего турнира Арена сама пишет в группу


# ---------------------------------------------------------
# Кнопки
# ---------------------------------------------------------

@router.callback_query(F.data.in_({"mt:join", "mt:leave"}))
async def signup_button(callback: CallbackQuery):
    from database.repository import get_mini_signup, save_mini_signup

    if callback.message is None:
        return
    chat_id = callback.message.chat.id
    user = callback.from_user
    async with _lock(chat_id):
        signup = await get_mini_signup(chat_id)
        if signup is None or signup.message_id != callback.message.message_id:
            await callback.answer("Запись уже закрыта.", show_alert=True)
            return
        players = list(signup.players or [])
        inside = any(p["id"] == user.id for p in players)

        if callback.data == "mt:leave":
            if not inside:
                await callback.answer("Тебя и так нет в списке 🙂")
                return
            players = [p for p in players if p["id"] != user.id]
            await save_mini_signup(chat_id, players=players)
            await callback.answer("Ты вышел из списка.")
            await _refresh(callback, signup.prize, players)
            return

        if inside:
            await callback.answer("Ты уже записан ✅")
            return
        if len(players) >= SEATS:
            await callback.answer("Мест нет — стол набран.", show_alert=True)
            return
        players.append({"id": user.id, "name": display_name_of(user)[:64], "username": user.username})
        await save_mini_signup(chat_id, players=players)
        await callback.answer(f"Ты в турнире! Место {len(players)} из {SEATS} 🎉")

        if len(players) < SEATS:
            await _refresh(callback, signup.prize, players)
            return

        # Стол набран: кнопки убираем и передаём состав Арене
        await _refresh(callback, signup.prize, players, closed=True)
        await launch(callback.message, signup, players)


async def _refresh(callback: CallbackQuery, prize: int, players: list[dict], closed: bool = False) -> None:
    try:
        await callback.message.edit_text(
            signup_text(prize, players, closed=closed),
            reply_markup=None if closed else signup_keyboard(),
        )
    except Exception as error:
        # «message is not modified» и прочее — список уже актуален
        logger.info("MINI SIGNUP EDIT: %s", error)


async def launch(message: Message, signup, players: list[dict]) -> None:
    from database.repository import delete_mini_signup

    chat_id = message.chat.id
    body = {
        "chatId": str(chat_id),
        "title": "Мини-турнир",
        "prize": int(signup.prize),
        "organizer": {"telegramId": str(signup.organizer_id), "name": signup.organizer_name},
        "players": [{"telegramId": str(p["id"]), "name": p["name"], "username": p.get("username")} for p in players],
    }
    status, answer = await _arena("POST", "mini-tournaments", body=body)
    await delete_mini_signup(chat_id)
    if status == 200:
        logger.info("MINI TOURNAMENT: стол набран в %s, турнир %s", chat_id, answer.get("id"))
        return
    logger.warning("MINI TOURNAMENT: Арена не приняла турнир в %s: %s %s", chat_id, status, answer)
    await message.answer(
        "😔 Не получилось открыть стол в Арене — она не отвечает. "
        "Админ, запусти турнир ещё раз: <code>/старт турнир " + str(signup.prize) + "</code>"
    )
