"""
Мини-турнир группы: запись у Мары, игра в Маруська Арене.

    /старт турнир 5000   — админ группы открывает запись; 5000 — приз в «Дурак Онлайн»
    /старт турнир2 5000  — то же на два стола: победители столов играют финал 1 на 1
    /стоп турнир         — отменить запись или идущий турнир

Мара публикует сообщение с кнопками «Записаться» и «Передумал» и сразу
дописывает в него каждого, кто записался. На шестом запись закрывается сама,
кнопки пропадают, и Мара передаёт состав Арене. Дальше всё ведёт Арена: сажает
всех за один стол, после каждой партии пишет в группу, кто остался дураком и
выбыл, и даёт ссылку на новый стол — на одного меньше. Победителя поздравляет
в группе, а организатору пишет в личку, кому выдать приз.

На два стола мест вдвое больше. Когда запись набрана, Арена сажает записавшихся
по очереди за стол А и стол Б, оба стола играют на вылет одновременно, а их
победители — финал 1 на 1.

Запись хранится в базе (mini_signups): перезапуск бота её не теряет.

Настройки (места, ожидание у стола, правила, текст объявления и картинка) —
общие для всех групп, меняются в админке: Арена → Мини-турниры. Запись
запоминает их на момент открытия, так что правка в админке её не ломает.
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
SETTINGS_KEY = "mini_tournament_settings"
# Подпись к фото в Telegram — до 1024 видимых символов: текст плюс список участников
MAX_TEXT = 450
MAX_NAME = 40

DEFAULT_TEXT = (
    "🏆 **Мини-турнир по дураку!**\n"
    "{rules}\n\n"
    "🎁 Призовой фонд: **{prize} кредитов в игре «Дурак Онлайн»** — всё забирает победитель.\n"
    "🃏 Играем в Маруська Арене: {format}. "
    "Не зашёл за стол за {seconds} с — техническое поражение."
)
# Прежний текст по умолчанию: он мог сохраниться в настройках, а «один стол» в нём — неправда для двух столов
OLD_DEFAULT_TEXT = DEFAULT_TEXT.replace("{format}", "один стол, после каждой партии дурак выбывает, пока не останется один")
# Имя в списке записи на два стола — короче: 12 строк должны влезть в подпись к картинке
MAX_NAME_TWO_TABLES = 16

DEFAULTS = {
    "seats": SEATS,
    "ready_seconds": 60,
    "variant": "perevodnoy",
    "throw_in": "all",
    "speed": "fast",
    "text": DEFAULT_TEXT,
    "photo": None,
    # Сколько столов — не из админки, а из команды: /старт турнир2
    "tables": 1,
}
LIMITS = {"seats": (2, 6), "ready_seconds": (15, 300), "tables": (1, 2)}
CHOICES = {"variant": ("perevodnoy", "podkidnoy"), "throw_in": ("all", "neighbors"), "speed": ("fast", "normal")}
RULE_NAMES = {
    "perevodnoy": "Переводной", "podkidnoy": "Подкидной",
    "all": "подкидывают все", "neighbors": "подкидывают соседи",
    "fast": "быстрая игра", "normal": "обычная скорость",
}
GROUP_CHATS = ("group", "supergroup")

_locks: dict[int, asyncio.Lock] = {}

NOT_CONNECTED = "🃏 Арена сейчас не подключена — турнир не запустить. Попробуйте позже."


def _lock(chat_id: int) -> asyncio.Lock:
    if chat_id not in _locks:
        _locks[chat_id] = asyncio.Lock()
    return _locks[chat_id]


def credits(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def parse_start(args: str | None) -> tuple[str, int | None, int] | None:
    """
    Аргументы «/старт турнир 5000» → ('start', 5000, 1); «турнир2 5000» — на два стола → ('start', 5000, 2);
    без суммы — ('start', None, столы). Не «турнир» — None.
    """
    words = (args or "").lower().replace("ё", "е").split()
    match = re.fullmatch(r"турнира?(2?)", words[0]) if words else None
    if match is None:
        return None
    rest = "".join(words[1:])
    digits = re.sub(r"[^\d]", "", rest)
    return "start", int(digits) if digits else None, 2 if match.group(1) else 1


def mention(player: dict) -> str:
    return f'<a href="tg://user?id={player["id"]}">{escape(player["name"])}</a>'


# ---------------------------------------------------------
# Настройки (админка: Арена → Мини-турниры)
# ---------------------------------------------------------

def clean_settings(raw: dict | None) -> dict:
    result = dict(DEFAULTS)
    for key, value in (raw or {}).items():
        if key in LIMITS:
            low, high = LIMITS[key]
            try:
                result[key] = max(low, min(high, int(value)))
            except (TypeError, ValueError):
                pass
        elif key in CHOICES and value in CHOICES[key]:
            result[key] = value
        elif key == "text" and isinstance(value, str) and value.strip():
            result["text"] = value.strip()[:MAX_TEXT]
        elif key == "photo":
            result["photo"] = value if isinstance(value, dict) and value.get("file_id") else None
    return result


async def load_settings() -> dict:
    from database.repository import get_group_settings

    return clean_settings((await get_group_settings(0)).get(SETTINGS_KEY))


async def save_settings(data: dict) -> dict:
    from database.repository import set_group_setting

    cleaned = clean_settings({**(await load_settings()), **(data or {})})
    await set_group_setting(chat_id=0, key=SETTINGS_KEY, value=cleaned)
    return cleaned


def rules_line(settings: dict) -> str:
    return " · ".join(RULE_NAMES[settings[k]] for k in ("variant", "throw_in", "speed")) + " · без ничьей"


def total_seats(settings: dict) -> int:
    """Мест в записи: «места» из админки — за одним столом."""
    return settings["seats"] * settings.get("tables", 1)


def format_line(settings: dict) -> str:
    if settings.get("tables", 1) == 2:
        return (f"два стола по {settings['seats']}, за каждым после партии дурак выбывает, пока не останется один, "
                "а победители столов играют финал 1 на 1")
    return "один стол, после каждой партии дурак выбывает, пока не останется один"


def render_intro(settings: dict, prize: int) -> str:
    """
    Текст из админки: HTML экранируется, **жирный** — жирным, {prize} {seats} {seconds} {rules} {format}
    подставляются (по разу). В своём тексте без {format} про два стола дописывается строка в конце.
    """
    raw = DEFAULT_TEXT if settings["text"] == OLD_DEFAULT_TEXT else settings["text"]
    text = escape(raw)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    two = settings.get("tables", 1) == 2
    if two and "{format}" not in text:
        text += "\n🃏🃏 " + format_line(settings)[0].upper() + format_line(settings)[1:] + "."
    for name, value in (("prize", credits(prize)), ("seats", str(total_seats(settings))),
                        ("seconds", str(settings["ready_seconds"])), ("rules", rules_line(settings)),
                        ("format", format_line(settings))):
        # Каждая подстановка — один раз: иначе длинный текст разрастётся и не влезет в подпись к картинке
        text = text.replace("{" + name + "}", value, 1)
    return text


def signup_text(prize: int, players: list[dict], closed: bool = False, settings: dict | None = None) -> str:
    settings = settings or DEFAULTS
    seats = total_seats(settings)
    if settings.get("tables", 1) > 1:
        players = [{**p, "name": p["name"][:MAX_NAME_TWO_TABLES]} for p in players]
    lines = [f"{i}. {mention(p)}" for i, p in enumerate(players, start=1)]
    lines += [f"{i}. —" for i in range(len(players) + 1, seats + 1)]
    body = render_intro(settings, prize) + f"\n\nУчастники ({len(players)}/{seats}):\n" + "\n".join(lines)
    if closed:
        body += ("\n\n✅ <b>Столы набраны — запись закрыта.</b> Сейчас пришлю ссылки на оба стола."
                 if settings.get("tables", 1) > 1 else
                 "\n\n✅ <b>Стол набран — запись закрыта.</b> Сейчас пришлю ссылку на стол.")
    return body


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
    await open_signup(message, parsed[1], parsed[2])


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


async def open_signup(message: Message, prize: int | None, tables: int = 1) -> None:
    from database.repository import get_mini_signup, save_mini_signup

    organizer = await _organizer(message)
    if organizer is None:
        await message.reply("🏆 Запускать турнир могут только админы группы.")
        return
    if prize is None:
        await message.reply(
            "🏆 Укажи призовой фонд: <code>/старт турнир 5000</code> — кредиты в «Дурак Онлайн» победителю.\n"
            "На два стола: <code>/старт турнир2 5000</code>"
        )
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

        settings = {**await load_settings(), "tables": tables}
        text = signup_text(prize, [], settings=settings)
        sent = None
        if settings["photo"]:
            try:
                sent = await message.answer_photo(settings["photo"]["file_id"], caption=text, reply_markup=signup_keyboard())
            except Exception as error:
                # Картинка пропала или подпись не влезла — объявление уйдёт текстом
                logger.warning("MINI SIGNUP PHOTO: %s %s", type(error).__name__, error)
                settings = {**settings, "photo": None}
        if sent is None:
            sent = await message.answer(text, reply_markup=signup_keyboard())
        await save_mini_signup(
            chat_id, message_id=sent.message_id, prize=prize,
            organizer_id=organizer[0], organizer_name=organizer[1][:128], players=[], settings=settings,
        )
    logger.info("MINI TOURNAMENT: запись открыта в %s, приз %s, столов %s", chat_id, prize, tables)


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
            cancelled = "🛑 <b>Мини-турнир отменён.</b> Запись закрыта."
            try:
                if (signup.settings or {}).get("photo"):
                    await message.bot.edit_message_caption(caption=cancelled, chat_id=chat_id, message_id=signup.message_id)
                else:
                    await message.bot.edit_message_text(cancelled, chat_id=chat_id, message_id=signup.message_id)
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
        settings = clean_settings(signup.settings)
        seats = total_seats(settings)
        inside = any(p["id"] == user.id for p in players)

        if callback.data == "mt:leave":
            if not inside:
                await callback.answer("Тебя и так нет в списке 🙂")
                return
            players = [p for p in players if p["id"] != user.id]
            await save_mini_signup(chat_id, players=players)
            await callback.answer("Ты вышел из списка.")
            await _refresh(callback, signup.prize, players, settings)
            return

        if inside:
            await callback.answer("Ты уже записан ✅")
            return
        if len(players) >= seats:
            await callback.answer("Мест нет — стол набран.", show_alert=True)
            return
        players.append({"id": user.id, "name": display_name_of(user)[:MAX_NAME], "username": user.username})
        await save_mini_signup(chat_id, players=players)
        await callback.answer(f"Ты в турнире! Место {len(players)} из {seats} 🎉")

        if len(players) < seats:
            await _refresh(callback, signup.prize, players, settings)
            return

        # Стол набран: кнопки убираем и передаём состав Арене
        await _refresh(callback, signup.prize, players, settings, closed=True)
        await launch(callback.message, signup, players, settings)


async def _refresh(callback: CallbackQuery, prize: int, players: list[dict], settings: dict, closed: bool = False) -> None:
    text = signup_text(prize, players, closed=closed, settings=settings)
    markup = None if closed else signup_keyboard()
    try:
        if settings.get("photo"):
            await callback.message.edit_caption(caption=text, reply_markup=markup)
        else:
            await callback.message.edit_text(text, reply_markup=markup)
    except Exception as error:
        # «message is not modified» и прочее — список уже актуален
        logger.info("MINI SIGNUP EDIT: %s", error)


async def launch(message: Message, signup, players: list[dict], settings: dict) -> None:
    from database.repository import delete_mini_signup

    chat_id = message.chat.id
    body = {
        "chatId": str(chat_id),
        "title": "Мини-турнир",
        "prize": int(signup.prize),
        "organizer": {"telegramId": str(signup.organizer_id), "name": signup.organizer_name},
        "players": [{"telegramId": str(p["id"]), "name": p["name"], "username": p.get("username")} for p in players],
        "tables": settings.get("tables", 1),
        "rules": {
            "variant": settings["variant"], "throwIn": settings["throw_in"],
            "speed": settings["speed"], "readySeconds": settings["ready_seconds"],
        },
    }
    status, answer = await _arena("POST", "mini-tournaments", body=body)
    await delete_mini_signup(chat_id)
    if status == 200:
        logger.info("MINI TOURNAMENT: стол набран в %s, турнир %s", chat_id, answer.get("id"))
        return
    logger.warning("MINI TOURNAMENT: Арена не приняла турнир в %s: %s %s", chat_id, status, answer)
    await message.answer(
        "😔 Не получилось открыть стол в Арене — она не отвечает. "
        "Админ, запусти турнир ещё раз: <code>/старт турнир" + ("2" if settings.get("tables", 1) == 2 else "")
        + " " + str(signup.prize) + "</code>"
    )
