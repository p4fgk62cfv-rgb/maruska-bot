"""
Крокодил.

Правила:
  - ведущим становится победитель прошлого раунда, а если такого
    нет — любой, кто первым нажмёт кнопку;
  - слово показывается ведущему во всплывающем окне, так что личка
    с ботом никому не нужна;
  - ведущий объясняет словами, не используя однокоренные;
  - первый, кто написал слово в чат, побеждает;
  - таймера нет, раунд живёт до отгадки, сдачи или /stopgame;
  - победителю и ведущему по +1 к рейтингу.
"""

import logging
import os
import re
import secrets
import time
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
    add_drawing_like,
    bump_counter,
    add_karma,
    change_balance,
    get_round,
    bump_game_stats,
    create_round,
    finish_round,
    get_last_winner,
    load_active_rounds,
    save_user,
    update_round,
)

from economy.service import (
    CURRENCY,
    REWARD_GAME_HOST,
    REWARD_GAME_WIN,
    plural,
)

from progress.service import award, level_up_text, unlocked_text
from progress.xp import XP_GAME_HOST, XP_GAME_WIN, XP_LIKE

from settings.store import get_number, is_enabled

from games import state
from games.words import LEVEL_NAMES, is_correct_guess, pick_word


logger = logging.getLogger("maruska.crocodile")

router = Router(name="crocodile")

GROUP_CHATS = ("group", "supergroup")

KARMA_FOR_WIN = 1

# Короткое имя Mini App из BotFather (/newapp). Пусто — играем
# словесной версией: ведущий объясняет текстом.
WEBAPP_SHORT_NAME = os.getenv("WEBAPP_SHORT_NAME", "").strip()

# Имя бота проставляется при старте: оно нужно для ссылки на Mini App
BOT_USERNAME = ""


def set_bot_username(username: str) -> None:
    global BOT_USERNAME
    BOT_USERNAME = username or ""


def drawing_enabled() -> bool:
    return bool(WEBAPP_SHORT_NAME and BOT_USERNAME)


def draw_url(token: str) -> str:
    return (
        f"https://t.me/{BOT_USERNAME}/{WEBAPP_SHORT_NAME}"
        f"?startapp={token}"
    )

START_RE = re.compile(r"\bкрокодил\w*\b", re.IGNORECASE)

# Сколько букв можно открыть подсказками (не больше половины слова)
HINT_LIMIT_RATIO = 0.5

# Пауза между буквами, чтобы слово не вскрыли за пять секунд
HINT_COOLDOWN = int(os.getenv("HINT_COOLDOWN", "30") or 30)


def masked_word(word: str, revealed: int = 0) -> str:
    """
    Слово ячейками: "ПОКРЫШКА" -> "П О ▢ ▢ ▢ ▢ ▢ ▢"

    Открываются буквы слева направо, пробелы показываются как есть.
    """
    cells = []
    opened = 0

    for char in word.upper():
        if char == " ":
            cells.append(" ")
            continue

        if opened < revealed:
            cells.append(char)
            opened += 1
        else:
            cells.append("▢")

    return " ".join(cells)


def hint_limit(word: str, chat_id: int | None = None) -> int:
    letters = len(word.replace(" ", ""))

    percent = None

    if chat_id is not None:
        try:
            from settings.store import get_number as _get_number

            percent = _get_number(chat_id, "hint_max_percent")
        except Exception:
            percent = None

    ratio = (percent / 100) if percent else HINT_LIMIT_RATIO

    return max(1, int(letters * ratio))


def crocodile_on(chat_id: int) -> bool:
    """Игры включены в группе и сам Крокодил не выключен отдельно."""
    return is_enabled(chat_id, "games") and is_enabled(chat_id, "game_crocodile")


def game_rules(chat_id: int) -> dict:
    """
    Все награды и правила раунда — из настроек группы.

    Одно место на всю игру: раньше часть значений читалась из
    настроек, а часть оставалась константами, и админка показывала
    одно, а игра платила другое.
    """
    def pick(key: str, fallback: int) -> int:
        value = get_number(chat_id, key)
        return fallback if value is None else value

    return {
        "win_prize": pick("reward_game_win", REWARD_GAME_WIN),
        "host_prize": pick("reward_game_host", REWARD_GAME_HOST),
        "karma": pick("karma_game_win", KARMA_FOR_WIN),
        "xp_win": pick("xp_game_win", XP_GAME_WIN),
        "xp_host": pick("xp_game_host", XP_GAME_HOST),
    }

# Слово должно быть командой, а не частью разговора:
# "давай крокодил" — да, "вчера видел крокодила в зоопарке" — нет.
MAX_START_WORDS = 4

_WORDS_RE = re.compile(r"[А-Яа-яЁёA-Za-z]+")


# ---------------------------------------------------------
# Клавиатуры
# ---------------------------------------------------------

def host_keyboard(token: str = "") -> InlineKeyboardMarkup:
    rows = []

    if token and drawing_enabled():
        rows.append([
            InlineKeyboardButton(
                text="🎨 Рисовать",
                url=draw_url(token),
            ),
        ])
    else:
        rows.append([
            InlineKeyboardButton(
                text="👀 Показать слово",
                callback_data="croc:show",
            ),
        ])

    rows.append([
        InlineKeyboardButton(
            text="🔄 Другое слово",
            callback_data="croc:swap",
        ),
        InlineKeyboardButton(
            text="🏳 Сдаюсь",
            callback_data="croc:give_up",
        ),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def drawing_keyboard(round_id: int, token: str, likes: int = 0) -> InlineKeyboardMarkup:
    """
    Клавиатура под присланным рисунком: лайк всем, «Дорисовать» художнику.
    """
    like_text = f"👍 Лайк ({likes})" if likes else "👍 Лайк"

    rows = [[
        InlineKeyboardButton(
            text=like_text,
            callback_data=f"croc:like:{round_id}",
        ),
    ]]

    if token and drawing_enabled():
        rows[0].append(
            InlineKeyboardButton(
                text="🎨 Дорисовать",
                url=draw_url(token),
            )
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def hint_keyboard(revealed: int, limit: int) -> InlineKeyboardMarkup | None:
    """
    Кнопка под ячейками. Когда открывать больше нечего — кнопки нет.
    """
    if revealed >= limit:
        return None

    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text=f"💡 Открыть букву ({revealed}/{limit})",
                callback_data="croc:hint",
            ),
        ]]
    )


def hint_text(word: str, revealed: int, limit: int) -> str:
    letters = len(word.replace(" ", ""))

    head = f"<code>{masked_word(word, revealed)}</code>\n\nБукв: {letters}"

    if revealed >= limit:
        return head + "\n\nБольше подсказок нет — дальше сами 😏"

    return head


async def ensure_hint_message(bot, item) -> None:
    """
    Вешает под рисунком табло с ячейками. Вызывается один раз
    за раунд — дальше сообщение только обновляется.
    """
    if item is None or item.hint_message_id:
        return

    limit = hint_limit(item.word, item.chat_id)

    try:
        sent = await bot.send_message(
            chat_id=item.chat_id,
            text=hint_text(item.word, 0, limit),
            reply_markup=hint_keyboard(0, limit),
        )
        item.hint_message_id = sent.message_id
    except Exception as error:
        logger.warning("HINT BOARD: %s %s", type(error).__name__, error)


def want_keyboard() -> InlineKeyboardMarkup:
    """
    Кнопка после раунда: любой может забрать ход и начать новый круг,
    не дожидаясь, пока победитель напишет «крокодил».
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="🖐 Хочу рисовать!",
                callback_data="croc:want",
            ),
        ]]
    )


def rules_text(host_name: str, extra: str = "") -> str:
    if drawing_enabled():
        how = (
            "Жми «Рисовать» — откроется холст, слово увидишь только ты.\n"
            "Рисунок уйдёт в чат, остальные отгадывают."
        )
    else:
        how = (
            "Жми «Показать слово» и объясняй словами. Однокоренные "
            "слова запрещены 😏"
        )

    return (
        "🐊 <b>Крокодил</b>\n\n"
        f"{extra}Ведущий — <b>{escape(host_name)}</b>.\n\n"
        f"{how}"
    )


def claim_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎭 Я ведущий",
                    callback_data="croc:claim",
                ),
            ]
        ]
    )


def display_name(user) -> str:
    return user.first_name or user.username or "Игрок"


# ---------------------------------------------------------
# Восстановление после перезапуска
# ---------------------------------------------------------

async def restore_rounds():
    try:
        rounds = await load_active_rounds()
    except Exception as error:
        logger.warning("RESTORE: %s", error)
        return 0

    for item in rounds:
        state.start(
            state.Round(
                round_id=item.id,
                chat_id=item.chat_id,
                host_id=item.host_telegram_id,
                host_name=item.host_name or "Игрок",
                word=item.word or "",
                level=item.level or "easy",
                status=item.status,
                token=item.token or "",
                message_id=item.message_id,
            )
        )

    return len(rounds)


# ---------------------------------------------------------
# Старт раунда
# ---------------------------------------------------------

def is_start_request(message: Message) -> bool:
    if message.chat.type not in GROUP_CHATS:
        return False

    if not crocodile_on(message.chat.id):
        return False

    if not message.text or message.text.startswith("/"):
        return False

    if not START_RE.search(message.text):
        return False

    return len(_WORDS_RE.findall(message.text)) <= MAX_START_WORDS


@router.message(Command("crocodile", "croc"))
@router.message(is_start_request)
async def start_round(message: Message):
    if not message.from_user:
        return

    if message.chat.type not in GROUP_CHATS:
        await message.answer("🐊 В крокодила играют компанией, добавь меня в чат.")
        return

    if not crocodile_on(message.chat.id):
        await message.reply(
            "🐊 Игры в этой группе выключены. "
            "Администратор может включить их в /settings."
        )
        return

    current = state.get(message.chat.id)

    if current:
        await message.reply(
            f"🐊 Раунд уже идёт, ведущий — <b>{escape(current.host_name)}</b>.\n"
            "Отгадывайте или /stopgame, чтобы остановить."
        )
        return

    # Ведущим становится победитель прошлого раунда
    previous = await get_last_winner(message.chat.id)

    if previous and previous.winner_telegram_id:
        word, level = pick_word()
        token = secrets.token_urlsafe(12)

        item = await create_round(
            chat_id=message.chat.id,
            host_telegram_id=previous.winner_telegram_id,
            host_name=previous.winner_name,
            word=word,
            level=level,
            token=token,
        )

        state.start(
            state.Round(
                round_id=item.id,
                chat_id=message.chat.id,
                host_id=previous.winner_telegram_id,
                host_name=previous.winner_name or "Игрок",
                word=word,
                level=level,
                token=token,
            )
        )

        sent = await message.answer(
            rules_text(
                previous.winner_name or "победитель",
                extra="Победитель прошлого раунда ведёт. ",
            ),
            reply_markup=host_keyboard(token),
        )

        await update_round(item.id, message_id=sent.message_id)
        return

    # Первая игра в чате — ведущего выбираем по кнопке
    sent = await message.answer(
        "🐊 <b>Крокодил</b>\n\n"
        "Первый раунд в этом чате — ведущего выбираем добровольно.\n"
        "Кто объясняет?",
        reply_markup=claim_keyboard(),
    )

    word, level = pick_word()
    token = secrets.token_urlsafe(12)

    item = await create_round(
        chat_id=message.chat.id,
        host_telegram_id=0,
        host_name=None,
        word=word,
        level=level,
        token=token,
    )

    state.start(
        state.Round(
            round_id=item.id,
            chat_id=message.chat.id,
            host_id=0,
            host_name="",
            word=word,
            level=level,
            token=token,
            message_id=sent.message_id,
        )
    )

    await update_round(item.id, message_id=sent.message_id)


# ---------------------------------------------------------
# Кнопки
# ---------------------------------------------------------

def _callback_chat_id(callback: CallbackQuery) -> int | None:
    message = callback.message
    return message.chat.id if message is not None else None


@router.callback_query(F.data == "croc:claim")
async def claim_host(callback: CallbackQuery):
    chat_id = _callback_chat_id(callback)

    if chat_id is None:
        await callback.answer("Сообщение недоступно", show_alert=True)
        return

    item = state.get(chat_id)

    if item is None:
        await callback.answer("Раунд уже закончился", show_alert=True)
        return

    if item.host_id:
        await callback.answer(
            f"Ведущий уже есть — {item.host_name}",
            show_alert=True,
        )
        return

    user = callback.from_user

    item.host_id = user.id
    item.host_name = display_name(user)

    await save_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    await update_round(
        item.round_id,
        host_telegram_id=user.id,
        host_name=item.host_name,
    )

    await callback.message.edit_text(
        rules_text(item.host_name),
        reply_markup=host_keyboard(item.token),
    )

    await callback.answer(
        "Ты ведущий! Открывай холст"
        if drawing_enabled()
        else "Ты ведущий! Жми «Показать слово»"
    )


@router.callback_query(F.data == "croc:show")
async def show_word(callback: CallbackQuery):
    chat_id = _callback_chat_id(callback)

    if chat_id is None:
        await callback.answer("Сообщение недоступно", show_alert=True)
        return

    item = state.get(chat_id)

    if item is None:
        await callback.answer("Раунд уже закончился", show_alert=True)
        return

    if callback.from_user.id != item.host_id:
        await callback.answer(
            "Слово только для ведущего 😏",
            show_alert=True,
        )
        return

    if item.status == "waiting":
        item.status = "playing"
        await update_round(item.round_id, status="playing")
        await ensure_hint_message(callback.bot, item)

    level = LEVEL_NAMES.get(item.level, "")

    await callback.answer(
        f"Твоё слово:\n\n{item.word.upper()}\n\n({level})",
        show_alert=True,
    )


@router.callback_query(F.data == "croc:swap")
async def swap_word(callback: CallbackQuery):
    chat_id = _callback_chat_id(callback)

    if chat_id is None:
        await callback.answer("Сообщение недоступно", show_alert=True)
        return

    item = state.get(chat_id)

    if item is None:
        await callback.answer("Раунд уже закончился", show_alert=True)
        return

    if callback.from_user.id != item.host_id:
        await callback.answer("Только ведущий меняет слово", show_alert=True)
        return

    word, level = pick_word()

    item.word = word
    item.level = level
    item.status = "playing"

    await update_round(
        item.round_id,
        word=word,
        level=level,
        status="playing",
    )

    if drawing_enabled():
        await callback.answer(
            f"Новое слово: {word.upper()}\n\n"
            "Открой холст заново — там оно уже обновилось.",
            show_alert=True,
        )
        return

    await callback.answer(
        f"Новое слово:\n\n{word.upper()}\n\n({LEVEL_NAMES.get(level, '')})",
        show_alert=True,
    )


@router.callback_query(F.data == "croc:give_up")
async def give_up(callback: CallbackQuery):
    chat_id = _callback_chat_id(callback)

    if chat_id is None:
        await callback.answer("Сообщение недоступно", show_alert=True)
        return

    item = state.get(chat_id)

    if item is None:
        await callback.answer("Раунд уже закончился", show_alert=True)
        return

    if callback.from_user.id != item.host_id:
        await callback.answer("Сдаться может только ведущий", show_alert=True)
        return

    state.drop(item.chat_id)

    await finish_round(
        item.round_id,
        winner_telegram_id=None,
        winner_name=None,
        status="cancelled",
    )

    await callback.message.edit_text(
        "🏳 <b>Ведущий сдался.</b>\n\n"
        f"Слово было: <b>{escape(item.word)}</b>",
        reply_markup=want_keyboard(),
    )

    await callback.answer("Раунд закрыт")


# ---------------------------------------------------------
# Подсказка буквами
# ---------------------------------------------------------

@router.callback_query(F.data == "croc:hint")
async def give_hint(callback: CallbackQuery):
    chat_id = _callback_chat_id(callback)

    if chat_id is None:
        await callback.answer("Сообщение недоступно", show_alert=True)
        return

    item = state.get(chat_id)

    if item is None:
        await callback.answer("Раунд уже закончился", show_alert=True)
        return

    # Подсказку может просить любой: она нужна отгадывающим,
    # а не ведущему.
    if callback.from_user.id == item.host_id:
        await callback.answer(
            "Ты и так знаешь слово 😏",
            show_alert=True,
        )
        return

    limit = hint_limit(item.word, chat_id)

    if item.hints_used >= limit:
        await callback.answer("Больше подсказок нет", show_alert=True)
        return

    cooldown = get_number(chat_id, "hint_cooldown")

    if cooldown is None:
        cooldown = HINT_COOLDOWN

    waited = time.monotonic() - item.last_hint_at

    if item.last_hint_at and waited < cooldown:
        left = int(cooldown - waited) + 1
        await callback.answer(
            f"Следующая буква через {left} сек",
            show_alert=True,
        )
        return

    item.hints_used += 1
    item.last_hint_at = time.monotonic()

    text = hint_text(item.word, item.hints_used, limit)
    markup = hint_keyboard(item.hints_used, limit)

    try:
        if item.hint_message_id:
            await callback.bot.edit_message_text(
                chat_id=chat_id,
                message_id=item.hint_message_id,
                text=text,
                reply_markup=markup,
            )
        else:
            sent = await callback.message.answer(text, reply_markup=markup)
            item.hint_message_id = sent.message_id
    except Exception as error:
        logger.warning("HINT: %s %s", type(error).__name__, error)

    await callback.answer(f"Открыта буква {item.hints_used} из {limit}")


# ---------------------------------------------------------
# Лайк рисунку
# ---------------------------------------------------------

@router.callback_query(F.data.startswith("croc:like:"))
async def like_drawing(callback: CallbackQuery):
    try:
        round_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer()
        return

    item = await get_round(round_id)

    if item is None:
        await callback.answer("Рисунок потерялся", show_alert=True)
        return

    if callback.from_user.id == item.host_telegram_id:
        await callback.answer("Свой рисунок лайкать нескромно 😏", show_alert=True)
        return

    counted, total = await add_drawing_like(round_id, callback.from_user.id)

    if not counted:
        await callback.answer(f"Уже лайкнул. Всего: {total}")
        return

    chat_id = _callback_chat_id(callback)

    # Художнику капает за признание
    if item.host_telegram_id:
        if is_enabled(chat_id, "economy"):
            await change_balance(
                telegram_id=item.host_telegram_id,
                amount=1,
                reason="game_host",
                note="Лайк рисунку",
                chat_id=item.chat_id,
                display_name=item.host_name,
            )

        if is_enabled(chat_id, "progress"):
            try:
                await bump_counter(item.host_telegram_id, "likes_received")

                await award(
                    telegram_id=item.host_telegram_id,
                    amount=XP_LIKE,
                    display_name=item.host_name,
                    chat_id=item.chat_id,
                    with_economy=is_enabled(chat_id, "economy"),
                )
            except Exception as error:
                logger.warning("LIKE XP: %s %s", type(error).__name__, error)

    try:
        await callback.message.edit_reply_markup(
            reply_markup=drawing_keyboard(round_id, item.token or "", total)
        )
    except Exception:
        pass

    await callback.answer(f"Красиво! Всего лайков: {total}")


# ---------------------------------------------------------
# Хочу рисовать
# ---------------------------------------------------------

@router.callback_query(F.data == "croc:want")
async def want_to_draw(callback: CallbackQuery):
    chat_id = _callback_chat_id(callback)

    if chat_id is None:
        await callback.answer("Сообщение недоступно", show_alert=True)
        return

    if not crocodile_on(chat_id):
        await callback.answer("Игры выключены в этой группе", show_alert=True)
        return

    if state.get(chat_id) is not None:
        await callback.answer("Раунд уже идёт", show_alert=True)
        return

    user = callback.from_user
    host_name = display_name(user)

    await save_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    word, level = pick_word()
    token = secrets.token_urlsafe(12)

    item = await create_round(
        chat_id=chat_id,
        host_telegram_id=user.id,
        host_name=host_name,
        word=word,
        level=level,
        token=token,
    )

    state.start(
        state.Round(
            round_id=item.id,
            chat_id=chat_id,
            host_id=user.id,
            host_name=host_name,
            word=word,
            level=level,
            token=token,
        )
    )

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    sent = await callback.message.answer(
        rules_text(host_name, extra="Ход забрал первый желающий. "),
        reply_markup=host_keyboard(token),
    )

    await update_round(item.id, message_id=sent.message_id)

    await callback.answer("Твой ход! Открывай холст")


# ---------------------------------------------------------
# Остановка
# ---------------------------------------------------------

@router.message(Command("stopgame"))
async def stop_game(message: Message):
    if not crocodile_on(message.chat.id):
        return

    item = state.drop(message.chat.id)

    if item is None:
        await message.reply("Сейчас никто не играет 🐊")
        return

    await finish_round(
        item.round_id,
        winner_telegram_id=None,
        winner_name=None,
        status="cancelled",
    )

    await message.answer(
        "🛑 Раунд остановлен.\n"
        f"Слово было: <b>{escape(item.word)}</b>",
        reply_markup=want_keyboard(),
    )


# ---------------------------------------------------------
# Отгадка
# ---------------------------------------------------------

def is_guess(message: Message) -> bool:
    """
    Синхронный фильтр: пропускаем дальше всё, кроме верной отгадки.
    Обычная переписка во время раунда работает как обычно.
    """
    if not message.text or message.text.startswith("/"):
        return False

    if not message.from_user or message.from_user.is_bot:
        return False

    item = state.get(message.chat.id)

    if item is None or item.status != "playing":
        return False

    if message.from_user.id == item.host_id:
        return False

    return is_correct_guess(message.text, item.word)


@router.message(is_guess)
async def handle_guess(message: Message):
    item = state.drop(message.chat.id)

    if item is None:
        return

    user = message.from_user
    winner_name = display_name(user)

    await save_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    await finish_round(
        item.round_id,
        winner_telegram_id=user.id,
        winner_name=winner_name,
    )

    rules = game_rules(message.chat.id)

    import audit

    audit.count(message.chat.id, "games")

    win_prize = rules["win_prize"]
    host_prize_amount = rules["host_prize"]
    karma_amount = rules["karma"]

    winner_karma = await add_karma(user.id, karma_amount, winner_name)
    await bump_game_stats(user.id, played=1, won=1, display_name=winner_name)

    # Алмазы — только если экономика включена в этой группе
    with_economy = is_enabled(message.chat.id, "economy")
    prize_line = ""

    if with_economy and win_prize:
        await change_balance(
            telegram_id=user.id,
            amount=win_prize,
            reason="game_win",
            note="Победа в Крокодиле",
            chat_id=message.chat.id,
            display_name=winner_name,
        )
        prize_line = (
            f"{CURRENCY} <b>+{win_prize}</b> {plural(win_prize)}\n"
        )

    host_line = ""

    if item.host_id:
        await add_karma(item.host_id, karma_amount, item.host_name)
        await bump_game_stats(
            item.host_id,
            played=1,
            display_name=item.host_name,
        )

        host_prize = ""

        if with_economy and host_prize_amount:
            await change_balance(
                telegram_id=item.host_id,
                amount=host_prize_amount,
                reason="game_host",
                note="Ведущий в Крокодиле",
                chat_id=message.chat.id,
                display_name=item.host_name,
            )
            host_prize = f" и {CURRENCY} <b>+{host_prize_amount}</b>"

        host_line = (
            f"🎭 Ведущий <b>{escape(item.host_name)}</b> получает "
            f"<b>+{karma_amount}</b> к рейтингу{host_prize}.\n"
        )

    # Опыт и достижения обоим
    progress_notes = []

    if is_enabled(message.chat.id, "progress"):
        for player_id, player_name, xp_amount in (
            (user.id, winner_name, rules["xp_win"]),
            (item.host_id, item.host_name, rules["xp_host"]),
        ):
            if not player_id:
                continue

            try:
                outcome = await award(
                    telegram_id=player_id,
                    amount=xp_amount,
                    display_name=player_name,
                    chat_id=message.chat.id,
                    with_economy=with_economy,
                )

                if outcome.get("level_up"):
                    progress_notes.append(
                        level_up_text(player_name, outcome["level"])
                    )

                if outcome.get("unlocked"):
                    progress_notes.append(
                        unlocked_text(
                            player_name,
                            outcome["unlocked"],
                            outcome.get("reward", 0),
                            with_economy,
                        )
                    )
            except Exception as error:
                logger.warning("GAME XP: %s %s", type(error).__name__, error)

    await message.reply(
        f"🎉 <b>{escape(winner_name)}</b> угадал!\n\n"
        f"Слово: <b>{escape(item.word)}</b>\n"
        f"⭐ <b>+{karma_amount}</b> к рейтингу, теперь <b>{winner_karma}</b>\n"
        f"{prize_line}"
        f"{host_line}\n"
        f"Следующий ведущий — <b>{escape(winner_name)}</b>.\n"
        "Или пусть ход заберёт кто-то другой:",
        reply_markup=want_keyboard(),
    )

    for note in progress_notes:
        if note:
            try:
                await message.answer(note)
            except Exception:
                pass
