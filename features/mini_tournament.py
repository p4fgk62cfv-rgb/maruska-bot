"""
Мини-турнир группы: запись у Мары, игра в Маруська Арене.

    /старт турнир 5000   — админ группы открывает запись; 5000 — приз в «Дурак Онлайн»
    /старт турнир2 5000  — то же на два стола: победители столов играют финал 1 на 1
    /старт турнир групп 5000 — турнир двух групп: Мара спросит, с какой группой; стол
                           каждой группы набирается в ней, победители играют финал
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

Турнир групп: запись открывается сразу в двух группах (у каждой своё сообщение и свои
места). Набравшийся стол ждёт второй; когда набраны оба, Арена сажает каждую группу за
свой стол, ссылка на стол — в своей группе, финал и итоги — в обеих. Отмена в любой из
двух групп отменяет обе записи.

Один человек — один турнир: кто уже в записи в другой группе или ещё не выбыл из
идущего там турнира, сюда не записывается. Иначе стол здесь ждал бы, пока он
доиграет там.

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
# Проверка «не записан ли в другой группе» и сама запись — без гонки между группами
_join_lock = asyncio.Lock()

NOT_CONNECTED = "🃏 Арена сейчас не подключена — турнир не запустить. Попробуйте позже."


def _lock(chat_id: int) -> asyncio.Lock:
    if chat_id not in _locks:
        _locks[chat_id] = asyncio.Lock()
    return _locks[chat_id]


def credits(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def parse_start(args: str | None) -> tuple[str, int | None, int, bool] | None:
    """
    Аргументы «/старт турнир 5000» → ('start', 5000, 1, False); «турнир2 5000» — на два стола →
    ('start', 5000, 2, False); «турнир групп 5000» — турнир двух групп → ('start', 5000, 2, True);
    без суммы — ('start', None, …). Не «турнир» — None.
    """
    words = (args or "").lower().replace("ё", "е").split()
    match = re.fullmatch(r"турнира?(2?)", words[0]) if words else None
    if match is None:
        return None
    groups = any(w.startswith("груп") for w in words[1:])
    rest = "".join(words[1:])
    digits = re.sub(r"[^\d]", "", rest)
    return "start", int(digits) if digits else None, 2 if match.group(1) or groups else 1, groups


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
        elif key == "link" and isinstance(value, dict) and value.get("chat"):
            # Турнир групп: вторая группа, названия обеих и чей стол первый (группа организатора)
            result["link"] = {"chat": int(value["chat"]), "title": str(value.get("title") or "")[:64],
                              "own": str(value.get("own") or "")[:64], "table": 1 if value.get("table") else 0}
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
    """Мест в записи: «места» из админки — за одним столом. В турнире групп у каждой группы свой стол."""
    return settings["seats"] * (1 if settings.get("link") else settings.get("tables", 1))


def format_line(settings: dict) -> str:
    link = settings.get("link")
    if link:
        return (f"турнир групп «{link['own']}» × «{link['title']}»: здесь свой стол, в «{link['title']}» — свой; "
                "за каждым после партии дурак выбывает, пока не останется один, а победители столов играют финал 1 на 1")
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
    two = settings.get("tables", 1) == 2 or bool(settings.get("link"))
    if two and "{format}" not in text:
        text += "\n🃏🃏 " + format_line(settings)[0].upper() + format_line(settings)[1:] + "."
    for name, value in (("prize", credits(prize)), ("seats", str(total_seats(settings))),
                        ("seconds", str(settings["ready_seconds"])), ("rules", rules_line(settings)),
                        ("format", format_line(settings))):
        # Каждая подстановка — один раз: иначе длинный текст разрастётся и не влезет в подпись к картинке
        text = text.replace("{" + name + "}", value, 1)
    return text


def signup_text(prize: int, players: list[dict], closed: bool = False, settings: dict | None = None,
                waiting: bool = False) -> str:
    """closed — запись закрыта; waiting — турнир групп: свой стол набран, ждём стол второй группы."""
    settings = settings or DEFAULTS
    seats = total_seats(settings)
    if settings.get("tables", 1) > 1 and not settings.get("link"):
        players = [{**p, "name": p["name"][:MAX_NAME_TWO_TABLES]} for p in players]
    lines = [f"{i}. {mention(p)}" for i, p in enumerate(players, start=1)]
    lines += [f"{i}. —" for i in range(len(players) + 1, seats + 1)]
    body = render_intro(settings, prize) + f"\n\nУчастники ({len(players)}/{seats}):\n" + "\n".join(lines)
    link = settings.get("link")
    if closed:
        body += ("\n\n✅ <b>Оба стола набраны — запись закрыта.</b> Сейчас пришлю ссылку на стол." if link else
                 "\n\n✅ <b>Столы набраны — запись закрыта.</b> Сейчас пришлю ссылки на оба стола."
                 if settings.get("tables", 1) > 1 else
                 "\n\n✅ <b>Стол набран — запись закрыта.</b> Сейчас пришлю ссылку на стол.")
    elif waiting and link:
        body += f"\n\n✅ <b>Стол набран.</b> Ждём, пока наберётся стол в «{escape(link['title'])}» — тогда начнём."
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
    if parsed[3]:
        await choose_partner(message, parsed[1])
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
            "На два стола: <code>/старт турнир2 5000</code>\n"
            "Турнир двух групп: <code>/старт турнир групп 5000</code>"
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
            cancelled = "🛑 <b>Мини-турнир отменён.</b> Запись закрыта."
            async with _join_lock:
                await delete_mini_signup(chat_id)
                await _edit_signup(message.bot, chat_id, signup, cancelled, None)
                # Турнир групп: вторая группа узнаёт об отмене в своём сообщении
                link = clean_settings(signup.settings).get("link")
                partner = await get_mini_signup(link["chat"]) if link else None
                if partner is not None:
                    await delete_mini_signup(link["chat"])
                    await _edit_signup(message.bot, link["chat"], partner, cancelled, None)
            await message.reply("🛑 Запись на турнир отменена." + (" Во второй группе — тоже." if partner is not None else ""))
            return
    status, answer = await _arena("POST", "mini-tournaments/cancel", body={"chatId": str(chat_id)})
    if status == 503:
        await message.reply(NOT_CONNECTED)
    elif not answer.get("cancelled"):
        await message.reply("🏆 Сейчас в группе нет турнира.")
    # Об отмене идущего турнира Арена сама пишет в группу


async def _group_name(bot, chat_id: int) -> str:
    try:
        title = (await bot.get_chat(chat_id)).title
    except Exception:
        title = None
    # Окно с ответом на кнопку — до 200 символов
    return f"в группе «{title[:40]}»" if title else "в другой группе"


async def busy_elsewhere(bot, chat_id: int, user_id: int) -> str | None:
    """Почему человеку нельзя записаться здесь: он в записи или в турнире другой группы. None — можно."""
    from database.repository import mini_signups_with

    signed = await mini_signups_with(user_id, exclude_chat=chat_id)
    if signed:
        where = await _group_name(bot, signed[0])
        return f"Ты уже записан на турнир {where}. В два турнира сразу нельзя — сначала нажми там «Передумал»."
    try:
        status, answer = await asyncio.wait_for(
            _arena("GET", "mini-tournaments/playing", query={"telegramId": str(user_id)}), timeout=5)
    except asyncio.TimeoutError:
        # Арена не ответила вовремя — запись не держим
        return None
    playing = answer.get("tournament") if status == 200 else None
    if playing and str(playing.get("chatId")) != str(chat_id):
        where = await _group_name(bot, int(playing["chatId"]))
        return f"Ты сейчас играешь турнир {where}. Записаться сюда можно, когда выбудешь или он закончится."
    return None


# ---------------------------------------------------------
# Турнир групп: выбор второй группы
# ---------------------------------------------------------

async def _chat_title(bot, chat_id: int) -> str | None:
    try:
        return (await bot.get_chat(chat_id)).title
    except Exception:
        return None


async def _is_admin_in(bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    return member.status in ("creator", "administrator")


async def _busy_group(chat_id: int) -> str | None:
    """Почему в группе сейчас не открыть запись: уже идёт запись или турнир. None — можно."""
    from database.repository import get_mini_signup

    if await get_mini_signup(chat_id):
        return "уже идёт запись на турнир"
    status, running = await _arena("GET", "mini-tournaments/active", query={"chatId": str(chat_id)})
    if status == 503:
        return "Арена не подключена"
    if status == 200 and running.get("tournament"):
        return "уже идёт турнир"
    return None


async def choose_partner(message: Message, prize: int | None) -> None:
    """«/старт турнир групп 5000»: кнопки с другими группами, где запускающий тоже админ."""
    from database.repository import list_known_chats

    if message.from_user is None or message.sender_chat is not None:
        await message.reply("🏆 Турнир групп запускается не анонимно: Мара проверит, что ты админ и во второй группе.")
        return
    if await _organizer(message) is None:
        await message.reply("🏆 Запускать турнир могут только админы группы.")
        return
    if prize is None:
        await message.reply("🏆 Укажи призовой фонд: <code>/старт турнир групп 5000</code>")
        return
    if prize > MAX_PRIZE:
        await message.reply("🏆 Слишком большой приз — проверь число.")
        return
    busy = await _busy_group(message.chat.id)
    if busy:
        await message.reply(f"🏆 Здесь {busy}. Отменить: /стоп турнир")
        return
    buttons = []
    for chat in await list_known_chats():
        chat_id = int(chat.get("chat_id") or chat.get("id") or 0)
        if not chat_id or chat_id == message.chat.id or chat_id > 0:
            continue
        from settings import access

        # Вторая группа должна тоже иметь доступ к Арене (его включает владелец бота)
        if not access.allowed(chat_id, "arena") or not await _is_admin_in(message.bot, chat_id, message.from_user.id):
            continue
        title = await _chat_title(message.bot, chat_id)
        if title:
            buttons.append([InlineKeyboardButton(
                text=title[:40], callback_data=f"mtg:{message.from_user.id}:{chat_id}:{prize}")])
        if len(buttons) >= 10:
            break
    if not buttons:
        await message.reply("🏆 Не нашла другой группы, где есть я и где ты тоже админ.")
        return
    await message.reply(
        f"🤝 <b>Турнир групп</b> · приз {credits(prize)} кредитов в «Дурак Онлайн»\n\n"
        "С какой группой играем? В каждой группе наберётся свой стол, а победители столов сыграют финал 1 на 1.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("mtg:"))
async def partner_button(callback: CallbackQuery):
    from database.repository import save_mini_signup

    if callback.message is None:
        return
    try:
        _, organizer_id, partner_id, prize = callback.data.split(":")
        organizer_id, partner_id, prize = int(organizer_id), int(partner_id), int(prize)
    except ValueError:
        return
    user = callback.from_user
    if user.id != organizer_id:
        await callback.answer("Группу выбирает тот, кто запускал турнир.", show_alert=True)
        return
    bot = callback.message.bot
    chat_id = callback.message.chat.id
    if not (await _is_admin_in(bot, chat_id, user.id) and await _is_admin_in(bot, partner_id, user.id)):
        await callback.answer("Нужно быть админом в обеих группах.", show_alert=True)
        return
    own_title = callback.message.chat.title or await _chat_title(bot, chat_id) or "Группа"
    partner_title = await _chat_title(bot, partner_id)
    from settings import access

    if not access.allowed(partner_id, "arena"):
        await callback.answer("Во второй группе Арена не включена.", show_alert=True)
        return
    if not partner_title:
        await callback.answer("Мары нет во второй группе.", show_alert=True)
        return
    async with _lock(chat_id), _join_lock:
        for group, title in ((chat_id, own_title), (partner_id, partner_title)):
            busy = await _busy_group(group)
            if busy:
                await callback.answer(f"В «{title[:40]}» {busy}.", show_alert=True)
                return
        base = await load_settings()
        name = display_name_of(user)[:128]
        opened = []
        for group, own, other, table in ((chat_id, own_title, partner_title, 0), (partner_id, partner_title, own_title, 1)):
            settings = {**base, "tables": 2, "link": {"chat": partner_id if table == 0 else chat_id,
                                                       "title": other, "own": own, "table": table}}
            settings = clean_settings(settings)
            sent, settings = await _post_signup(bot, group, signup_text(prize, [], settings=settings), settings)
            if sent is None:
                await callback.answer(f"Не получилось написать в «{own[:40]}».", show_alert=True)
                break
            await save_mini_signup(group, message_id=sent.message_id, prize=prize, organizer_id=user.id,
                                   organizer_name=name, players=[], settings=settings)
            opened.append(group)
        if len(opened) < 2:
            return
    await callback.answer("Запись открыта в обеих группах 🎉")
    try:
        await callback.message.edit_text(f"🤝 Турнир групп «{escape(own_title)}» × «{escape(partner_title)}»: запись открыта в обеих группах.")
    except Exception:
        pass
    logger.info("MINI TOURNAMENT: турнир групп %s × %s, приз %s", chat_id, partner_id, prize)


async def _post_signup(bot, chat_id: int, text: str, settings: dict):
    """Сообщение записи в группу (с картинкой из админки, если есть). → (сообщение или None, настройки)."""
    if settings.get("photo"):
        try:
            return await bot.send_photo(chat_id, settings["photo"]["file_id"], caption=text, reply_markup=signup_keyboard()), settings
        except Exception as error:
            logger.warning("MINI SIGNUP PHOTO: %s %s", type(error).__name__, error)
            settings = {**settings, "photo": None}
    try:
        return await bot.send_message(chat_id, text, reply_markup=signup_keyboard()), settings
    except Exception as error:
        logger.warning("MINI SIGNUP SEND %s: %s", chat_id, error)
        return None, settings


async def _edit_signup(bot, chat_id: int, signup, text: str, markup) -> None:
    try:
        if (signup.settings or {}).get("photo"):
            await bot.edit_message_caption(caption=text, chat_id=chat_id, message_id=signup.message_id, reply_markup=markup)
        else:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=signup.message_id, reply_markup=markup)
    except Exception as error:
        # «message is not modified» и прочее — список уже актуален
        logger.info("MINI SIGNUP EDIT %s: %s", chat_id, error)


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
    bot = callback.message.bot
    # Список читается и меняется под общим замком: турнир групп смотрит и на запись второй группы
    async with _lock(chat_id), _join_lock:
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
            await _edit_signup(bot, chat_id, signup, signup_text(signup.prize, players, settings=settings), signup_keyboard())
            return

        if inside:
            await callback.answer("Ты уже записан ✅")
            return
        if len(players) >= seats:
            await callback.answer("Мест нет — стол набран.", show_alert=True)
            return
        reason = await busy_elsewhere(bot, chat_id, user.id)
        if reason:
            await callback.answer(reason, show_alert=True)
            return
        players.append({"id": user.id, "name": display_name_of(user)[:MAX_NAME], "username": user.username})
        await save_mini_signup(chat_id, players=players)
        await callback.answer(f"Ты в турнире! Место {len(players)} из {seats} 🎉")

        if len(players) < seats:
            await _edit_signup(bot, chat_id, signup, signup_text(signup.prize, players, settings=settings), signup_keyboard())
            return

        link = settings.get("link")
        if link:
            # Турнир групп: свой стол набран — начинаем, только когда набран и стол второй группы
            partner = await get_mini_signup(link["chat"])
            partner_settings = clean_settings(partner.settings) if partner else None
            if partner is None or len(partner.players or []) < total_seats(partner_settings):
                await _edit_signup(bot, chat_id, signup,
                                   signup_text(signup.prize, players, settings=settings, waiting=True), signup_keyboard())
                return
            for group, row, rows_players, row_settings in ((chat_id, signup, players, settings),
                                                           (link["chat"], partner, partner.players, partner_settings)):
                await _edit_signup(bot, group, row, signup_text(row.prize, rows_players, closed=True, settings=row_settings), None)
            await launch_groups(bot, (chat_id, signup, players, settings), (link["chat"], partner, list(partner.players), partner_settings))
            return

        # Стол набран: кнопки убираем и передаём состав Арене
        await _edit_signup(bot, chat_id, signup, signup_text(signup.prize, players, closed=True, settings=settings), None)
        await launch(callback.message, signup, players, settings)


def _rules(settings: dict) -> dict:
    return {"variant": settings["variant"], "throwIn": settings["throw_in"],
            "speed": settings["speed"], "readySeconds": settings["ready_seconds"]}


def _person(p: dict, **extra) -> dict:
    return {"telegramId": str(p["id"]), "name": p["name"], "username": p.get("username"), **extra}


async def launch_groups(bot, one: tuple, two: tuple) -> None:
    """Оба стола турнира групп набраны: Арене — обе группы, каждая за свой стол. (chat_id, запись, игроки, настройки)"""
    from database.repository import delete_mini_signup

    # Первый стол — группа организатора: там и приз, и сообщение организатору
    first, second = sorted((one, two), key=lambda g: g[3]["link"]["table"])
    signup, settings = first[1], first[3]
    body = {
        "chatId": str(first[0]),
        "title": "Турнир групп",
        "prize": int(signup.prize),
        "organizer": {"telegramId": str(signup.organizer_id), "name": signup.organizer_name},
        "tables": 2,
        "groups": [{"chatId": str(first[0]), "name": settings["link"]["own"] or "Группа 1"},
                   {"chatId": str(second[0]), "name": second[3]["link"]["own"] or "Группа 2"}],
        "players": [_person(p, table=0) for p in first[2]] + [_person(p, table=1) for p in second[2]],
        "rules": _rules(settings),
    }
    status, answer = await _arena("POST", "mini-tournaments", body=body)
    for group in (first[0], second[0]):
        await delete_mini_signup(group)
    if status == 200:
        logger.info("MINI TOURNAMENT: турнир групп %s × %s начат, %s", first[0], second[0], answer.get("id"))
        return
    logger.warning("MINI TOURNAMENT: Арена не приняла турнир групп %s × %s: %s %s", first[0], second[0], status, answer)
    for group in (first[0], second[0]):
        try:
            await bot.send_message(group, "😔 Не получилось открыть столы в Арене — она не отвечает. "
                                          f"Админ, запусти турнир ещё раз: <code>/старт турнир групп {signup.prize}</code>")
        except Exception:
            pass


async def launch(message: Message, signup, players: list[dict], settings: dict) -> None:
    from database.repository import delete_mini_signup

    chat_id = message.chat.id
    body = {
        "chatId": str(chat_id),
        "title": "Мини-турнир",
        "prize": int(signup.prize),
        "organizer": {"telegramId": str(signup.organizer_id), "name": signup.organizer_name},
        "players": [_person(p) for p in players],
        "tables": settings.get("tables", 1),
        "rules": _rules(settings),
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
