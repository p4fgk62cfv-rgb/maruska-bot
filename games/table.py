"""
Игры прямо в чате, на кнопках — без мини-приложения.

  /игры (/games)               — меню
  /крестики (/ttt)             — крестики-нолики
  /шашки [ставка] (/checkers)  — русские шашки, картинка доски
  /морской [ставка]            — морской бой 8×8, картинка полей
  /кнб [ставка] (/rps)         — камень-ножницы-бумага
  /орел [ставка] (/heads)      — орёл или решка: угадай; ответом на сообщение — дуэль

Соперника зовут ответом на его сообщение (вызов только ему) или без ответа —
тогда играет первый, кто нажмёт «Играю». В личке и кнопкой «С Маруськой» —
против бота.

Экономика (если в группе включена): ставка в 💎 — проигравший отдаёт её
победителю; за победу над человеком — награда и опыт из настроек; за победы
над Маруськой и в играх на удачу — меньше и не больше N раз в день.
Партии живут в памяти: после перезапуска бота начинаются заново (ставки
списываются только в конце партии, поэтому при перезапуске никто не теряет).
"""

import asyncio
import datetime
import logging
import random
import re
import secrets
import time
from dataclasses import dataclass, field
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Message,
)

from botcontext import display_name_of
from games import table_art as art
from games.table_core import (
    RPS, SIZE, Checkers, Sea, rps_result, sea_bot_target, side_of, ttt_bot_move, ttt_line, ttt_winner,
)
from settings.store import get_number, is_enabled

logger = logging.getLogger("maruska.table")
router = Router(name="table_games")

BOT_ID = 0
BOT_NAME = "Маруська"
IDLE = 2 * 3600
BLANK = "⠀"
SEA_LETTERS = "АБВГДЕЖЗ"
MAX_STAKE = 10_000

TITLES = {
    "ttt": "❌⭕ Крестики-нолики",
    "checkers": "⚫ Шашки",
    "sea": "🚢 Морской бой",
    "rps": "✊ Камень, ножницы, бумага",
    "coin": "🦅 Орёл или решка",
}
PHOTO_KINDS = {"checkers", "sea", "rps"}
LUCK_KINDS = {"rps", "coin"}


@dataclass
class Game:
    gid: str
    kind: str
    chat_id: int
    players: list[tuple[int, str]]
    invited: int | None = None
    status: str = "lobby"                      # lobby | playing | over
    state: object = None
    turn: int = 0                              # индекс игрока, который ходит
    turn_white: int = 0                        # шашки: кто играет белыми (они ходят первыми)
    selected: int | None = None                # шашки: выбранная шашка
    picks: dict = field(default_factory=dict)  # кнб: выборы
    score: list[int] = field(default_factory=lambda: [0, 0])
    last_winner: int | None = None
    stake: int = 0
    note: str = ""
    payout: str = ""
    touched: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def vs_bot(self) -> bool:
        return len(self.players) == 2 and self.players[1][0] == BOT_ID

    @property
    def photo(self) -> bool:
        return self.kind in PHOTO_KINDS

    def index_of(self, user_id: int) -> int | None:
        for i, (pid, _) in enumerate(self.players):
            if pid == user_id:
                return i
        return None

    def plain(self, i: int) -> str:
        return self.players[i][1]

    def name(self, i: int) -> str:
        return f"<b>{escape(self.players[i][1])}</b>"


_games: dict[str, Game] = {}


def _cleanup() -> None:
    now = time.monotonic()
    for gid in [g for g, game in _games.items() if now - game.touched > IDLE]:
        _games.pop(gid, None)


def games_on(chat_id: int) -> bool:
    # Отдельно от общего «Игры» (он по умолчанию выключен): эти игры включены сразу
    return chat_id > 0 or is_enabled(chat_id, "game_table")


OFF_TEXT = "♟ Игры в чате выключены в этой группе. Включить: /settings → Развлечения → «Игры в чате» или панель → Игры."


def btn(text: str, gid: str, act: str, arg: str | int = "") -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=f"tg:{gid}:{act}:{arg}")


def checkers_cell(pos: int) -> str:
    r, c = divmod(pos, 8)
    return f"{'abcdefgh'[c]}{8 - r}"


def sea_cell_name(pos: int) -> str:
    r, c = divmod(pos, SIZE)
    return f"{SEA_LETTERS[c]}{r + 1}"


def strip_tags(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    for mark in ("🏆 ", "🤝 ", "🏳 ", " 🏆", " 🦅", " 💰"):
        text = text.replace(mark, " " if mark.startswith(" ") else "")
    return text.strip()


# =========================================================
# ЭКОНОМИКА
# =========================================================

def economy_on(chat_id: int) -> bool:
    return is_enabled(chat_id, "economy")


def setting(chat_id: int, key: str, fallback: int) -> int:
    """Числа из настроек группы (в личке — значения по умолчанию)."""
    if chat_id >= 0:
        return fallback
    value = {
        "reward_table_win": lambda: get_number(chat_id, "reward_table_win"),
        "reward_table_luck": lambda: get_number(chat_id, "reward_table_luck"),
        "xp_table_win": lambda: get_number(chat_id, "xp_table_win"),
        "table_daily_cap": lambda: get_number(chat_id, "table_daily_cap"),
    }[key]()
    return fallback if value is None else value


_rewarded: dict[tuple[int, str], int] = {}


def _daily_left(user_id: int, chat_id: int) -> int:
    today = datetime.date.today().isoformat()
    for key in [k for k in _rewarded if k[1] != today]:
        _rewarded.pop(key, None)
    return setting(chat_id, "table_daily_cap", 10) - _rewarded.get((user_id, today), 0)


def _spend_daily(user_id: int) -> None:
    key = (user_id, datetime.date.today().isoformat())
    _rewarded[key] = _rewarded.get(key, 0) + 1


def parse_stake(message: Message) -> int:
    parts = (message.text or "").split()
    if len(parts) > 1 and parts[1].isdigit():
        return min(int(parts[1]), MAX_STAKE)
    return 0


async def balance(user_id: int) -> int:
    from database.repository import get_balance

    try:
        return await get_balance(user_id)
    except Exception:
        logger.exception("TABLE: balance failed")
        return 0


async def settle(game: Game, winner: int | None) -> str:
    """Ставка, награды, опыт и статистика по итогам партии. Возвращает строки для подписи."""
    from database.repository import bump_game_stats, change_balance
    from economy.service import CURRENCY

    chat_id = game.chat_id
    title = TITLES.get(game.kind, "Игра")
    lines = []
    try:
        for i in range(2):
            if game.players[i][0] != BOT_ID:
                await bump_game_stats(game.players[i][0], played=1, won=1 if i == winner else 0, display_name=game.plain(i))
    except Exception:
        logger.exception("TABLE: stats failed")
    if not economy_on(chat_id):
        return ""
    try:
        if game.stake and winner is not None and not game.vs_bot:
            loser = 1 - winner
            take = min(game.stake, await balance(game.players[loser][0]))
            if take > 0:
                await change_balance(game.players[loser][0], -take, "game_stake", f"Проигрыш: {title}", chat_id, game.plain(loser))
                await change_balance(game.players[winner][0], take, "game_win", f"Выигрыш ставки: {title}", chat_id, game.plain(winner))
                lines.append(f"{CURRENCY} {game.name(winner)} забирает ставку: <b>+{take}</b>")
        if winner is not None and game.players[winner][0] != BOT_ID:
            uid = game.players[winner][0]
            luck = game.kind in LUCK_KINDS
            prize = setting(chat_id, "reward_table_luck" if luck else "reward_table_win", 3 if luck else 15)
            xp = setting(chat_id, "xp_table_win", 30) // (3 if luck else 1)
            if game.vs_bot or luck:
                if _daily_left(uid, chat_id) <= 0:
                    lines.append("⏳ Награды за такие победы на сегодня закончились")
                    return "\n".join(lines)
                _spend_daily(uid)
                if game.vs_bot and not luck:
                    prize, xp = prize // 2, xp // 2
            if prize:
                await change_balance(uid, prize, "game_win", f"Победа: {title}", chat_id, game.plain(winner))
                lines.append(f"🏆 Награда {game.name(winner)}: {CURRENCY} <b>+{prize}</b>")
            if xp and is_enabled(chat_id, "progress"):
                from progress.service import award, level_up_text

                outcome = await award(telegram_id=uid, amount=xp, display_name=game.plain(winner), chat_id=chat_id)
                lines.append(f"✨ +{xp} опыта")
                if outcome.get("level_up"):
                    lines.append(level_up_text(game.plain(winner), outcome["level"]))
    except Exception:
        logger.exception("TABLE: settle failed")
    return "\n".join(lines)


# =========================================================
# ЛОББИ И СТАРТ
# =========================================================

def stake_line(game: Game) -> str:
    return f"\n💎 Ставка: <b>{game.stake}</b> — проигравший отдаёт победителю" if game.stake else ""


def lobby_view(game: Game):
    title = TITLES[game.kind]
    gid = game.gid
    if game.invited:
        text = f"{title}\n\n{game.name(0)} вызывает <b>{escape(game.note)}</b> на партию!"
        line = f"{game.plain(0)} вызывает {game.note}"
        rows = [[btn("✅ Принять вызов", gid, "join")]]
    else:
        text = f"{title}\n\n{game.name(0)} ищет соперника. Кто сыграет?"
        line = f"{game.plain(0)} ищет соперника"
        rows = [[btn("🙋 Играю!", gid, "join")]]
    text += stake_line(game)
    rows.append([btn("🤖 С Маруськой", gid, "bot"), btn("✖️ Отмена", gid, "cancel")])
    image = (lambda: art.cover_image(game.kind, line, game.stake)) if game.photo else None
    return text, InlineKeyboardMarkup(inline_keyboard=rows), image


def start(game: Game) -> None:
    game.status = "playing"
    game.selected = None
    game.picks = {}
    game.note = ""
    game.payout = ""
    if game.kind == "ttt":
        game.state = [""] * 9
    elif game.kind == "checkers":
        game.state = Checkers()
    elif game.kind == "sea":
        game.state = (Sea(), Sea())
    game.turn = random.randrange(2) if game.kind != "rps" else 0


# =========================================================
# ОТРИСОВКА
# =========================================================

def footer(game: Game, extra: list | None = None) -> list:
    if game.status == "over":
        return [[btn("🔄 Реванш", game.gid, "again")]]
    row = extra or []
    row.append(btn("🏳 Сдаться", game.gid, "give"))
    return [row]


def with_payout(game: Game, text: str) -> str:
    return text + (f"\n\n{game.payout}" if game.payout else "")


def ttt_view(game: Game):
    cells = game.state
    marks = ("❌", "⭕")
    line = ttt_line(cells) or ()
    head = f"{TITLES['ttt']}\n❌ {game.name(0)}  vs  ⭕ {game.name(1)}\n\n"
    head += game.note if game.status == "over" else f"Ходит {marks[game.turn]} {game.name(game.turn)}"
    rows = []
    for r in range(3):
        row = []
        for c in range(3):
            i = r * 3 + c
            mark = {"X": "❌", "O": "⭕"}.get(cells[i], BLANK)
            if i in line:
                mark = {"X": "✖️", "O": "🟢"}[cells[i]]
            row.append(btn(mark, game.gid, "m", i))
        rows.append(row)
    return with_payout(game, head), InlineKeyboardMarkup(inline_keyboard=rows + footer(game)), None


PIECES = {"w": "⚪", "W": "🤍", "b": "⚫", "B": "🖤"}


def checkers_view(game: Game):
    g: Checkers = game.state
    sides = {"w": game.turn_white, "b": 1 - game.turn_white}
    head = f"{TITLES['checkers']}: ⚪ {game.name(sides['w'])} vs ⚫ {game.name(sides['b'])}{stake_line(game)}\n\n"
    over = game.status == "over"
    if over:
        head += game.note
    else:
        hint = "бей дальше!" if g.chain is not None else ("куда ходим? (🟩)" if game.selected is not None else "нажми свою шашку на кнопках")
        head += f"Ходит {PIECES[g.turn]} {game.name(sides[g.turn])} — {hint}"
        if game.note:
            head += f"\n{game.note}"
    opts = g.options() if not over else {}
    targets = tuple(opts.get(game.selected, [])) if game.selected is not None else ()
    rows = []
    if not over:
        for r in range(8):
            row = []
            for c in range(8):
                pos = r * 8 + c
                if (r + c) % 2 == 0:
                    text = BLANK
                elif pos == game.selected:
                    text = "🟡"
                elif pos in targets:
                    text = "🟩"
                else:
                    text = PIECES.get(g.board[pos], "·")
                row.append(btn(text, game.gid, "c", pos))
            rows.append(row)
    board, names = list(g.board), (game.plain(sides["w"]), game.plain(sides["b"]))
    counts, turn, selected = (g.count("w"), g.count("b")), None if over else g.turn, game.selected
    captured, last, result = tuple(g.captured), g.last, strip_tags(game.note) if over else None

    def image():
        return art.checkers_image(board, names, counts, turn, selected=selected, targets=targets,
                                  captured=captured, last=last, result=result)
    return with_payout(game, head), InlineKeyboardMarkup(inline_keyboard=rows + footer(game)), image


def sea_cell(sea: Sea, pos: int) -> str:
    ship = sea.ship_at(pos)
    if pos in sea.shots:
        if not ship:
            return "•"
        return "🔥" if ship <= sea.shots else "💥"
    return "·"


def sea_view(game: Game):
    shooter = game.turn
    target = 1 - shooter
    seas: tuple[Sea, Sea] = game.state
    over = game.status == "over"
    head = f"{TITLES['sea']}: {game.name(0)} vs {game.name(1)}{stake_line(game)}\n\n"
    if over:
        head += game.note
    else:
        head += f"🎯 Стреляет {game.name(shooter)} — по полю {game.name(target)} (кнопки ниже)"
        if game.note:
            head += f"\n{game.note}"
    board = seas[target]
    rows = [] if over else [
        [btn(sea_cell(board, r * SIZE + c), game.gid, "s", r * SIZE + c) for c in range(SIZE)] for r in range(SIZE)
    ]
    names = (game.plain(0), game.plain(1))
    result = strip_tags(game.note) if over else None

    def image():
        return art.sea_image(seas, names, None if over else target, reveal=over, result=result)
    markup = InlineKeyboardMarkup(inline_keyboard=rows + footer(game, [btn("👁 Мои корабли", game.gid, "fleet")]))
    return with_payout(game, head), markup, image


def rps_view(game: Game):
    head = f"{TITLES['rps']}\n{game.name(0)}  {game.score[0]} : {game.score[1]}  {game.name(1)}{stake_line(game)}\n\n"
    names = (game.plain(0), game.plain(1))
    if game.status == "over":
        picks = tuple(game.picks.get(game.players[i][0]) for i in range(2))
        winner = game.last_winner
        result = strip_tags(game.note.split("\n")[-1])

        def image():
            return art.rps_image(names, picks, result, winner)
        return with_payout(game, head + game.note), InlineKeyboardMarkup(inline_keyboard=[[btn("🔄 Ещё раз", game.gid, "again")]]), image
    waiting = [game.name(i) for i in range(2) if game.players[i][0] not in game.picks and game.players[i][0] != BOT_ID]
    head += "Выбирайте! Выбор соперника скрыт до конца раунда.\nЖдём: " + ", ".join(waiting)
    row = [btn(f"{e} {n}", game.gid, "r", key) for key, (e, n) in RPS.items()]

    def image():
        return art.rps_image(names, (None, None))
    return head, InlineKeyboardMarkup(inline_keyboard=[row, [btn("✖️ Выйти", game.gid, "give")]]), image


def view(game: Game):
    if game.status == "lobby":
        return lobby_view(game)
    return {"ttt": ttt_view, "checkers": checkers_view, "sea": sea_view, "rps": rps_view}[game.kind](game)


async def render(image) -> BufferedInputFile:
    data = await asyncio.to_thread(image)
    return BufferedInputFile(data, filename="game.jpg")


async def send(message: Message, game: Game) -> Message:
    text, markup, image = view(game)
    if game.photo:
        return await message.answer_photo(await render(image), caption=text, reply_markup=markup)
    return await message.answer(text, reply_markup=markup)


async def redraw(message: Message, game: Game, picture: bool = True) -> None:
    text, markup, image = view(game)
    try:
        if game.photo and picture:
            media = InputMediaPhoto(media=await render(image), caption=text, parse_mode="HTML")
            await message.edit_media(media, reply_markup=markup)
        elif game.photo:
            await message.edit_caption(caption=text, reply_markup=markup)
        else:
            await message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as error:
        if "not modified" not in str(error):
            logger.warning("TABLE: redraw failed: %s", error)


# =========================================================
# ХОДЫ
# =========================================================

async def finish(game: Game, winner: int | None, text: str) -> None:
    game.status = "over"
    game.last_winner = winner
    if winner is not None:
        game.score[winner] += 1
    game.note = text
    game.payout = await settle(game, winner)


def ttt_play(game: Game, i: int) -> str | None:
    cells = game.state
    if cells[i]:
        return "Клетка занята"
    cells[i] = "XO"[game.turn]
    return None


async def ttt_after(game: Game) -> None:
    win = ttt_winner(game.state)
    if win == "draw":
        await finish(game, None, "🤝 Ничья! Силы равны.")
    elif win:
        w = "XO".index(win)
        await finish(game, w, f"🏆 Побеждает {game.name(w)}!")
    else:
        game.turn = 1 - game.turn


async def checkers_after(game: Game) -> None:
    g: Checkers = game.state
    sides = {"w": game.turn_white, "b": 1 - game.turn_white}
    if g.winner == "draw":
        await finish(game, None, "🤝 Ничья: 30 ходов дамками без взятий.")
    elif g.winner:
        w = sides[g.winner]
        await finish(game, w, f"🏆 Побеждает {game.name(w)}!")
    else:
        game.turn = sides[g.turn]


async def sea_fire(game: Game, pos: int) -> str:
    target = 1 - game.turn
    sea: Sea = game.state[target]
    result = sea.shoot(pos)
    where = sea_cell_name(pos)
    if result == "again":
        return "again"
    if result == "miss":
        game.note = f"{game.name(game.turn)}: {where} — мимо"
        game.turn = target
    elif result == "hit":
        game.note = f"{game.name(game.turn)}: {where} — 💥 ранил! Стреляй ещё"
    else:
        game.note = f"{game.name(game.turn)}: {where} — 🔥 потопил! Стреляй ещё"
    if sea.lost():
        await finish(game, game.turn, f"🏆 Побеждает {game.name(game.turn)} — флот соперника на дне!")
    return result


async def bot_turns(message: Message, game: Game) -> None:
    """Ходы Маруськи, пока очередь её."""
    while game.status == "playing" and game.vs_bot and game.turn == 1:
        await asyncio.sleep(0.8)
        if game.kind == "ttt":
            ttt_play(game, ttt_bot_move(game.state, "O"))
            await ttt_after(game)
        elif game.kind == "checkers":
            g: Checkers = game.state
            step = g.bot_step()
            if not step:
                break
            game.selected = None
            g.move(*step)
            game.note = f"Маруська: {checkers_cell(step[0])} → {checkers_cell(step[1])}"
            if g.chain is not None:
                continue  # бьёт дальше — картинку обновим в конце серии
            await checkers_after(game)
        elif game.kind == "sea":
            await sea_fire(game, sea_bot_target(game.state[0]))
        else:
            break
        await redraw(message, game)


async def resolve_rps(game: Game) -> None:
    a = game.picks[game.players[0][0]]
    b = game.picks[game.players[1][0]]
    res = rps_result(a, b)
    shown = f"{RPS[a][0]} {game.name(0)}  vs  {game.name(1)} {RPS[b][0]}\n"
    if res == 0:
        await finish(game, None, shown + "🤝 Ничья!")
    else:
        w = 0 if res == 1 else 1
        await finish(game, w, shown + f"🏆 Побеждает {game.name(w)}!")


# =========================================================
# КОМАНДЫ
# =========================================================

def command_is(*names: str):
    def check(message: Message) -> bool:
        head = ((message.text or "").strip().split(maxsplit=1) or [""])[0].lower()
        head = head.split("@", 1)[0]
        return head in names
    return check


async def check_stake(message: Message, user_id: int, stake: int) -> bool:
    if not stake:
        return True
    if not economy_on(message.chat.id):
        await message.answer("💎 Экономика в этой группе выключена — играем без ставки.")
        return False
    if await balance(user_id) < stake:
        await message.answer(f"💎 Не хватает алмазов на ставку {stake} — играем без ставки. Баланс: /balance")
        return False
    return True


async def create(message: Message, kind: str, opener=None, stake: int = 0) -> None:
    _cleanup()
    user = opener or message.from_user
    if not games_on(message.chat.id):
        await message.answer(OFF_TEXT)
        return
    if message.chat.type == "private" or not await check_stake(message, user.id, stake):
        stake = 0
    game = Game(gid=secrets.token_hex(4), kind=kind, chat_id=message.chat.id,
                players=[(user.id, display_name_of(user))], stake=stake)
    reply = message.reply_to_message if opener is None else None
    if reply and reply.from_user and not reply.from_user.is_bot and reply.from_user.id != user.id:
        game.invited = reply.from_user.id
        game.note = display_name_of(reply.from_user)
    _games[game.gid] = game
    if message.chat.type == "private":
        game.players.append((BOT_ID, BOT_NAME))
        start(game)
        game.turn_white = game.turn
    sent = await send(message, game)
    if game.status == "playing" and game.vs_bot and game.turn == 1:
        async with game.lock:
            await bot_turns(sent, game)


KINDS = {
    "ttt": "ttt", "крестики": "ttt", "checkers": "checkers", "шашки": "checkers",
    "seabattle": "sea", "морской": "sea", "rps": "rps", "кнб": "rps",
    "heads": "coin", "orel": "coin", "орел": "coin", "орёл": "coin", "монетка": "coin",
}


@router.message(Command("games", "ttt", "checkers", "seabattle", "rps", "heads", "orel"))
@router.message(command_is("/игры", "/крестики", "/шашки", "/морской", "/кнб", "/орел", "/орёл", "/монетка"))
async def table_command(message: Message):
    head = (message.text or "").strip().split(maxsplit=1)[0].lower().split("@", 1)[0].lstrip("/")
    kind = KINDS.get(head)
    stake = parse_stake(message)
    if kind == "coin":
        await coin_start(message, stake=stake)
    elif kind:
        await create(message, kind, stake=stake)
    else:
        await menu(message)


async def menu(message: Message) -> None:
    rows = [
        [InlineKeyboardButton(text="🐊 Крокодил", callback_data="tm:croc")],
        [InlineKeyboardButton(text="❌⭕ Крестики-нолики", callback_data="tm:ttt"),
         InlineKeyboardButton(text="⚫ Шашки", callback_data="tm:checkers")],
        [InlineKeyboardButton(text="🚢 Морской бой", callback_data="tm:sea"),
         InlineKeyboardButton(text="✊ Камень-ножницы", callback_data="tm:rps")],
        [InlineKeyboardButton(text="🦅 Орёл или решка", callback_data="tm:coin")],
    ]
    # Арена и Рыбалка — мини-приложения; кнопка только если игра сейчас доступна
    try:
        from features.arena_promo import games_buttons

        group = message.chat.type in ("group", "supergroup")
        rows += [[b] for b in await games_buttons(message.bot, message.chat.id, group)]
    except Exception:
        pass
    await message.answer(
        "🎲 <b>Игры Маруськи</b>\n\nВыбери игру — Маруська откроет стол прямо здесь.\n\n"
        "• Вызвать человека — ответь на его сообщение командой: /шашки, /морской, /кнб, /орел, /крестики\n"
        "• Сыграть на алмазы — добавь ставку: <code>/шашки 50</code> — проигравший отдаёт её победителю\n"
        "• За победы — 💎 и опыт; против Маруськи — поменьше",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("tm:"))
async def menu_pick(callback: CallbackQuery):
    kind = (callback.data or "").split(":", 1)[1]
    await callback.answer()
    if callback.message is None:
        return
    if kind == "croc":
        from games.crocodile import start_round

        await start_round(callback.message)
    elif kind == "coin":
        await coin_start(callback.message, opener=callback.from_user)
    elif kind in TITLES:
        await create(callback.message, kind, opener=callback.from_user)


# =========================================================
# ОРЁЛ ИЛИ РЕШКА
# =========================================================

def photo(data: bytes) -> BufferedInputFile:
    return BufferedInputFile(data, filename="coin.jpg")


SIDE = {"heads": ("🦅", "орёл", "за орла"), "tails": ("💰", "решка", "за решку")}


def other_side(side: str) -> str:
    return "tails" if side == "heads" else "heads"


def coin_btn(text: str, gid: str, act: str, arg: str = "") -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=f"tc:{gid}:{act}:{arg}")


def coin_view(game: Game) -> tuple[str, InlineKeyboardMarkup | None]:
    gid = game.gid
    side = game.picks.get("side")
    head = f"🦅 <b>Орёл или решка</b>{stake_line(game)}\n\n"
    if side is None:
        head += f"{game.name(0)}, выбери свою сторону 👇"
        if game.invited:
            head += f"\nСоперник — <b>{escape(game.note)}</b>"
        rows = [[coin_btn("🦅 Орёл", gid, "side", "heads"), coin_btn("💰 Решка", gid, "side", "tails")],
                [coin_btn("✖️ Отмена", gid, "cancel")]]
        return head, InlineKeyboardMarkup(inline_keyboard=rows)
    mine, theirs = SIDE[side], SIDE[other_side(side)]
    head += f"{game.name(0)} играет {mine[2]} {mine[0]}\n"
    if game.invited:
        head += f"<b>{escape(game.note)}</b>, принимаешь? Тебе — {theirs[1]} {theirs[0]}"
        rows = [[coin_btn(f"✅ Принять ({theirs[1]})", gid, "join")]]
    else:
        head += f"Кто против? Тебе достанется {theirs[1]} {theirs[0]}"
        rows = [[coin_btn(f"🙋 Играю {theirs[2]}", gid, "join")]]
    rows.append([coin_btn("🤖 Против Маруськи", gid, "bot"), coin_btn("✖️ Отмена", gid, "cancel")])
    return head, InlineKeyboardMarkup(inline_keyboard=rows)


async def coin_start(message: Message, opener=None, stake: int = 0) -> None:
    if not games_on(message.chat.id):
        await message.answer(OFF_TEXT)
        return
    _cleanup()
    user = opener or message.from_user
    if message.chat.type == "private" or not await check_stake(message, user.id, stake):
        stake = 0
    game = Game(gid=secrets.token_hex(4), kind="coin", chat_id=message.chat.id, stake=stake,
                players=[(user.id, display_name_of(user))])
    reply = message.reply_to_message if opener is None else None
    if reply and reply.from_user and not reply.from_user.is_bot and reply.from_user.id != user.id:
        game.invited = reply.from_user.id
        game.note = display_name_of(reply.from_user)
    _games[game.gid] = game
    text, markup = coin_view(game)
    image = await asyncio.to_thread(art.coin_image, "Орёл или решка?", None, f"{game.plain(0)} выбирает сторону")
    await message.answer_photo(photo(image), caption=text, reply_markup=markup)


async def coin_flip(message: Message, game: Game) -> None:
    side = game.picks["side"]
    first, second = SIDE[side], SIDE[other_side(side)]
    head = (f"🦅 <b>Орёл или решка</b>{stake_line(game)}\n\n"
            f"{first[0]} {game.name(0)} — {first[1]}\n{second[0]} {game.name(1)} — {second[1]}\n\n")
    try:
        await message.edit_caption(caption=head + "Монетка в воздухе… 🌀")
    except TelegramBadRequest:
        pass
    await asyncio.sleep(1.5)
    result = random.choice(("heads", "tails"))
    w = 0 if result == side else 1
    word = "Выпал орёл" if result == "heads" else "Выпала решка"
    await finish(game, w, f"{word}! Победа за {game.name(w)} 🏆")
    image = await asyncio.to_thread(art.coin_image, f"{word}!", result == "heads", f"Победа за {game.plain(w)}")
    rows = [[coin_btn("🔄 Ещё раз", game.gid, "new")]]
    await message.edit_media(InputMediaPhoto(media=photo(image), caption=with_payout(game, head + game.note), parse_mode="HTML"),
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("tc:"))
async def coin_press(callback: CallbackQuery):
    _, gid, act, arg = ((callback.data or "") + ":::").split(":")[:4]
    game = _games.get(gid)
    message = callback.message
    user = callback.from_user
    if act == "new":
        await callback.answer()
        if message:
            await coin_start(message, opener=user, stake=game.stake if game else 0)
        return
    if game is None or message is None:
        await callback.answer("Игра устарела — начните новую: /орел", show_alert=True)
        return
    async with game.lock:
        game.touched = time.monotonic()
        if game.status != "lobby":
            await callback.answer("Монетка уже подброшена")
            return
        me = game.index_of(user.id)
        if act == "cancel":
            if me != 0:
                await callback.answer("Отменить может только тот, кто начал")
                return
            _games.pop(gid, None)
            await callback.answer()
            try:
                await message.edit_caption(caption="🦅 Орёл или решка — отменено.")
            except TelegramBadRequest:
                pass
            return
        if act == "side":
            if me != 0:
                await callback.answer("Сторону выбирает тот, кто начал игру")
                return
            if arg not in SIDE:
                await callback.answer()
                return
            game.picks["side"] = arg
            await callback.answer(f"Ты играешь {SIDE[arg][2]}")
            if message.chat.type == "private":
                game.players.append((BOT_ID, BOT_NAME))
                game.status = "playing"
                await coin_flip(message, game)
                return
            text, markup = coin_view(game)
            try:
                await message.edit_caption(caption=text, reply_markup=markup)
            except TelegramBadRequest:
                pass
            return
        if "side" not in game.picks:
            await callback.answer("Сначала автор выбирает сторону")
            return
        if act == "bot":
            if me != 0:
                await callback.answer("Позвать Маруську может только тот, кто начал")
                return
            game.stake = 0
            game.players.append((BOT_ID, BOT_NAME))
        elif act == "join":
            if me == 0:
                await callback.answer("Ждём соперника — или нажми «Против Маруськи»")
                return
            if game.invited and user.id != game.invited:
                await callback.answer("Этот вызов не тебе 😉")
                return
            if game.stake and await balance(user.id) < game.stake:
                await callback.answer(f"Не хватает алмазов на ставку {game.stake} 💎", show_alert=True)
                return
            game.players.append((user.id, display_name_of(user)))
        else:
            await callback.answer()
            return
        game.status = "playing"
        await callback.answer("Подбрасываем!")
        await coin_flip(message, game)


# =========================================================
# НАЖАТИЯ В ПАРТИИ
# =========================================================

@router.callback_query(F.data.startswith("tg:"))
async def table_press(callback: CallbackQuery):
    _, gid, act, arg = ((callback.data or "") + ":::").split(":")[:4]
    game = _games.get(gid)
    message = callback.message
    if game is None or message is None:
        await callback.answer("Партия устарела — начните новую: /игры", show_alert=True)
        return
    user = callback.from_user
    async with game.lock:
        game.touched = time.monotonic()
        me = game.index_of(user.id)

        if act == "cancel":
            if me != 0 or game.status != "lobby":
                await callback.answer("Отменить может только тот, кто открыл стол")
                return
            _games.pop(gid, None)
            await callback.answer()
            try:
                if game.photo:
                    await message.edit_caption(caption=f"{TITLES[game.kind]}\n\nСтол закрыт.")
                else:
                    await message.edit_text(f"{TITLES[game.kind]}\n\nСтол закрыт.")
            except TelegramBadRequest:
                pass
            return

        if act in ("join", "bot"):
            if game.status != "lobby":
                await callback.answer("Игра уже началась")
                return
            if act == "bot":
                if me != 0:
                    await callback.answer("Позвать Маруську может только тот, кто открыл стол")
                    return
                game.stake = 0  # с Маруськой — без ставки
                game.players.append((BOT_ID, BOT_NAME))
            else:
                if me == 0:
                    await callback.answer("Ждём соперника — или нажми «С Маруськой»")
                    return
                if game.invited and user.id != game.invited:
                    await callback.answer("Этот вызов не тебе 😉")
                    return
                if game.stake and await balance(user.id) < game.stake:
                    await callback.answer(f"Не хватает алмазов на ставку {game.stake} 💎", show_alert=True)
                    return
                game.players.append((user.id, display_name_of(user)))
            start(game)
            game.turn_white = game.turn
            await callback.answer("Поехали!")
            await redraw(message, game)
            await bot_turns(message, game)
            return

        if act == "again":
            if game.status != "over" or me is None:
                await callback.answer("Реванш могут начать только игроки")
                return
            if game.stake and not game.vs_bot:
                for i in range(2):
                    if await balance(game.players[i][0]) < game.stake:
                        game.stake = 0
            first = 1 - game.turn_white
            start(game)
            if game.kind == "checkers":
                game.turn_white = game.turn = first
            else:
                game.turn_white = game.turn
            await callback.answer("Реванш!")
            await redraw(message, game)
            await bot_turns(message, game)
            return

        if act == "fleet":
            if me is None or game.kind != "sea" or game.status == "lobby":
                await callback.answer("Это для игроков")
                return
            sea: Sea = game.state[me]
            lines = []
            for r in range(SIZE):
                row = ""
                for c in range(SIZE):
                    pos = r * SIZE + c
                    ship = sea.ship_at(pos)
                    row += ("×" if pos in sea.shots else "■") if ship else ("•" if pos in sea.shots else "·")
                lines.append(row)
            await callback.answer("Твой флот (■ корабль, × подбит, • мимо):\n" + "\n".join(lines), show_alert=True)
            return

        if game.status != "playing":
            await callback.answer("Партия окончена" if game.status == "over" else "Ждём второго игрока")
            return
        if me is None:
            await callback.answer("Ты не в этой партии — открой свою: /игры")
            return

        if act == "give":
            other = 1 - me
            await finish(game, other, f"🏳 {game.name(me)} сдаётся. Победа за {game.name(other)}!")
            await callback.answer()
            await redraw(message, game)
            return

        if game.kind == "rps" and act == "r":
            if user.id in game.picks:
                await callback.answer("Ты уже выбрал(а)")
                return
            if arg not in RPS:
                await callback.answer()
                return
            game.picks[user.id] = arg
            if game.vs_bot:
                game.picks[BOT_ID] = random.choice(list(RPS))
            await callback.answer(f"Принято: {RPS[arg][1]}")
            if len(game.picks) == 2:
                await resolve_rps(game)
                await redraw(message, game)
            else:
                await redraw(message, game, picture=False)
            return

        if me != game.turn:
            await callback.answer("Сейчас не твой ход")
            return

        try:
            pos = int(arg)
        except ValueError:
            await callback.answer()
            return

        if game.kind == "ttt" and act == "m":
            problem = ttt_play(game, pos)
            if problem:
                await callback.answer(problem)
                return
            await ttt_after(game)

        elif game.kind == "checkers" and act == "c":
            g: Checkers = game.state
            opts = g.options()
            if pos in opts and g.chain is None:
                game.selected = pos
                await callback.answer()
                await redraw(message, game)
                return
            if game.selected is None:
                mine = side_of(g.board[pos]) == g.turn
                await callback.answer("Этой шашкой ходить нельзя — бить обязательно!" if mine and opts else "Выбери свою шашку")
                return
            if not g.move(game.selected, pos):
                await callback.answer("Сюда нельзя")
                return
            game.note = ""
            game.selected = g.chain
            if g.chain is None:
                await checkers_after(game)

        elif game.kind == "sea" and act == "s":
            if await sea_fire(game, pos) == "again":
                await callback.answer("Сюда уже стреляли")
                return

        else:
            await callback.answer()
            return

        await callback.answer()
        await redraw(message, game)
        await bot_turns(message, game)
