"""
Игры прямо в чате, на кнопках — без мини-приложения.

  /игры (/games)             — меню
  /крестики (/ttt)           — крестики-нолики
  /шашки (/checkers)         — русские шашки
  /морской (/seabattle)      — морской бой 8×8
  /кнб (/rps)                — камень-ножницы-бумага
  /орел, /орёл (/heads)      — орёл или решка: угадай; ответом на сообщение — дуэль

Соперника зовут ответом на его сообщение (вызов только ему) или без ответа —
тогда играет первый, кто нажмёт «Играю». В личке и кнопкой «С Маруськой» —
против бота. Партии живут в памяти: после перезапуска бота начинаются заново.
"""

import asyncio
import logging
import random
import secrets
import time
from dataclasses import dataclass, field
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from botcontext import display_name_of
from games.table_core import (
    RPS, SIZE, Checkers, Sea, rps_result, sea_bot_target, side_of, ttt_bot_move, ttt_line, ttt_winner,
)
from settings.store import is_enabled

logger = logging.getLogger("maruska.table")
router = Router(name="table_games")

BOT_ID = 0
BOT_NAME = "Маруська"
IDLE = 2 * 3600
BLANK = "⠀"
LETTERS = "АБВГДЕЖЗ"

TITLES = {
    "ttt": "❌⭕ Крестики-нолики",
    "checkers": "⚫ Шашки",
    "sea": "🚢 Морской бой",
    "rps": "✊ Камень, ножницы, бумага",
}


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
    note: str = ""
    touched: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def vs_bot(self) -> bool:
        return len(self.players) == 2 and self.players[1][0] == BOT_ID

    def index_of(self, user_id: int) -> int | None:
        for i, (pid, _) in enumerate(self.players):
            if pid == user_id:
                return i
        return None

    def name(self, i: int) -> str:
        return f"<b>{escape(self.players[i][1])}</b>"


_games: dict[str, Game] = {}


def _cleanup() -> None:
    now = time.monotonic()
    for gid in [g for g, game in _games.items() if now - game.touched > IDLE]:
        _games.pop(gid, None)


def games_on(chat_id: int) -> bool:
    return chat_id > 0 or (is_enabled(chat_id, "games") and is_enabled(chat_id, "game_table"))


def btn(text: str, gid: str, act: str, arg: str | int = "") -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=f"tg:{gid}:{act}:{arg}")


def cell_name(pos: int, size: int) -> str:
    r, c = divmod(pos, size)
    return f"{LETTERS[c]}{r + 1}"


# =========================================================
# ЛОББИ
# =========================================================

def lobby_view(game: Game) -> tuple[str, InlineKeyboardMarkup]:
    title = TITLES[game.kind]
    gid = game.gid
    if game.invited:
        text = f"{title}\n\n{game.name(0)} вызывает {escape(game.note)} на партию!"
        rows = [[btn("✅ Принять вызов", gid, "join")]]
    else:
        text = f"{title}\n\n{game.name(0)} ищет соперника. Кто сыграет?"
        rows = [[btn("🙋 Играю!", gid, "join")]]
    rows.append([btn("🤖 С Маруськой", gid, "bot"), btn("✖️ Отмена", gid, "cancel")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


def start(game: Game) -> None:
    game.status = "playing"
    game.selected = None
    game.picks = {}
    game.note = ""
    if game.kind == "ttt":
        game.state = [""] * 9
    elif game.kind == "checkers":
        game.state = Checkers()
    elif game.kind == "sea":
        game.state = (Sea(), Sea())   # флот игрока 0 и игрока 1
    # Кто начинает — по жребию; в реванше — по очереди
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


def ttt_view(game: Game) -> tuple[str, InlineKeyboardMarkup]:
    cells = game.state
    marks = ("❌", "⭕")
    line = ttt_line(cells) or ()
    head = f"{TITLES['ttt']}\n❌ {game.name(0)}  vs  ⭕ {game.name(1)}\n\n"
    if game.status == "over":
        head += game.note
    else:
        head += f"Ходит {marks[game.turn]} {game.name(game.turn)}"
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
    return head, InlineKeyboardMarkup(inline_keyboard=rows + footer(game))


PIECES = {"w": "⚪", "W": "🤍", "b": "⚫", "B": "🖤"}


def checkers_view(game: Game) -> tuple[str, InlineKeyboardMarkup]:
    g: Checkers = game.state
    # Игрок 0 играет белыми, если начинает он
    white = game.turn_white
    sides = {"w": white, "b": 1 - white}
    head = (
        f"{TITLES['checkers']}\n⚪ {game.name(sides['w'])} ({g.count('w')})  vs  "
        f"⚫ {game.name(sides['b'])} ({g.count('b')})\n\n"
    )
    if game.status == "over":
        head += game.note
    else:
        who = sides[g.turn]
        hint = "бей дальше!" if g.chain is not None else ("куда ходим?" if game.selected is not None else "выбери шашку")
        head += f"Ходит {PIECES[g.turn]} {game.name(who)} — {hint}"
        if game.note:
            head += f"\n{game.note}"
    opts = g.options() if game.status == "playing" else {}
    targets = set(opts.get(game.selected, [])) if game.selected is not None else set()
    rows = []
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
            elif pos in g.captured:
                text = "💥"
            else:
                text = PIECES.get(g.board[pos], "·")
            row.append(btn(text, game.gid, "c", pos))
        rows.append(row)
    return head, InlineKeyboardMarkup(inline_keyboard=rows + footer(game))


def sea_cell(sea: Sea, pos: int, reveal: bool) -> str:
    ship = sea.ship_at(pos)
    if pos in sea.shots:
        if not ship:
            return "•"
        return "❌" if ship <= sea.shots else "💥"
    if reveal and ship:
        return "🚢"
    return "·"


def sea_view(game: Game) -> tuple[str, InlineKeyboardMarkup]:
    shooter = game.turn
    target = 1 - shooter
    seas: tuple[Sea, Sea] = game.state
    board = seas[target]
    head = (
        f"{TITLES['sea']}\n{game.name(0)} 🚢{seas[0].alive()}  vs  🚢{seas[1].alive()} {game.name(1)}\n\n"
    )
    if game.status == "over":
        head += game.note
        board = seas[1] if game.vs_bot else board
    else:
        head += f"🎯 Стреляет {game.name(shooter)} — по флоту {game.name(target)}"
        if game.note:
            head += f"\n{game.note}"
    reveal = game.status == "over"
    rows = [[btn(sea_cell(board, r * SIZE + c, reveal), game.gid, "s", r * SIZE + c) for c in range(SIZE)] for r in range(SIZE)]
    return head, InlineKeyboardMarkup(inline_keyboard=rows + footer(game, [btn("👁 Мои корабли", game.gid, "fleet")]))


def rps_view(game: Game) -> tuple[str, InlineKeyboardMarkup]:
    head = f"{TITLES['rps']}\n{game.name(0)}  {game.score[0]} : {game.score[1]}  {game.name(1)}\n\n"
    if game.status == "over":
        head += game.note
        return head, InlineKeyboardMarkup(inline_keyboard=[[btn("🔄 Ещё раз", game.gid, "again")]])
    waiting = [game.name(i) for i in range(2) if game.players[i][0] not in game.picks and game.players[i][0] != BOT_ID]
    head += "Выбирайте! Выбор соперника скрыт до конца раунда.\nЖдём: " + ", ".join(waiting)
    row = [btn(f"{e} {n}", game.gid, "r", key) for key, (e, n) in RPS.items()]
    return head, InlineKeyboardMarkup(inline_keyboard=[row, [btn("✖️ Выйти", game.gid, "give")]])


def view(game: Game) -> tuple[str, InlineKeyboardMarkup]:
    if game.status == "lobby":
        return lobby_view(game)
    return {"ttt": ttt_view, "checkers": checkers_view, "sea": sea_view, "rps": rps_view}[game.kind](game)


async def redraw(message: Message, game: Game) -> None:
    text, markup = view(game)
    try:
        await message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as error:
        if "not modified" not in str(error):
            logger.warning("TABLE: redraw failed: %s", error)


# =========================================================
# ХОДЫ
# =========================================================

def finish(game: Game, winner: int | None, text: str) -> None:
    game.status = "over"
    if winner is not None:
        game.score[winner] += 1
    game.note = text


def ttt_play(game: Game, i: int) -> str | None:
    cells = game.state
    if cells[i]:
        return "Клетка занята"
    cells[i] = "XO"[game.turn]
    return None


def ttt_after(game: Game) -> None:
    win = ttt_winner(game.state)
    if win == "draw":
        finish(game, None, "🤝 Ничья! Силы равны.")
    elif win:
        w = "XO".index(win)
        finish(game, w, f"🏆 Побеждает {game.name(w)}!")
    else:
        game.turn = 1 - game.turn


def checkers_after(game: Game) -> None:
    g: Checkers = game.state
    white = game.turn_white
    sides = {"w": white, "b": 1 - white}
    if g.winner == "draw":
        finish(game, None, "🤝 Ничья: 30 ходов дамками без взятий.")
    elif g.winner:
        w = sides[g.winner]
        finish(game, w, f"🏆 Побеждает {game.name(w)}!")
    else:
        game.turn = sides[g.turn]


def sea_fire(game: Game, pos: int) -> str:
    target = 1 - game.turn
    sea: Sea = game.state[target]
    result = sea.shoot(pos)
    where = cell_name(pos, SIZE)
    if result == "again":
        return "again"
    if result == "miss":
        game.note = f"{game.name(game.turn)}: {where} — мимо"
        game.turn = target
    elif result == "hit":
        game.note = f"{game.name(game.turn)}: {where} — 💥 ранил! Стреляй ещё"
    else:
        game.note = f"{game.name(game.turn)}: {where} — ❌ потопил! Стреляй ещё"
    if sea.lost():
        finish(game, game.turn, f"🏆 {game.name(game.turn)} потопил(а) весь флот соперника!")
    return result


async def bot_turns(message: Message, game: Game) -> None:
    """Ходы Маруськи, пока очередь её."""
    while game.status == "playing" and game.vs_bot and game.turn == 1:
        await asyncio.sleep(0.8)
        if game.kind == "ttt":
            ttt_play(game, ttt_bot_move(game.state, "O"))
            ttt_after(game)
        elif game.kind == "checkers":
            g: Checkers = game.state
            step = g.bot_step()
            if not step:
                break
            game.selected = None
            g.move(*step)
            game.note = f"Маруська: {cell_name(step[0], 8)} → {cell_name(step[1], 8)}"
            if g.chain is None:
                checkers_after(game)
        elif game.kind == "sea":
            pos = sea_bot_target(game.state[0])
            sea_fire(game, pos)
        else:
            break
        await redraw(message, game)


def resolve_rps(game: Game) -> None:
    a = game.picks[game.players[0][0]]
    b = game.picks[game.players[1][0]]
    res = rps_result(a, b)
    shown = f"{RPS[a][0]} {game.name(0)}  vs  {game.name(1)} {RPS[b][0]}\n\n"
    if res == 0:
        finish(game, None, shown + "🤝 Ничья!")
    else:
        w = 0 if res == 1 else 1
        finish(game, w, shown + f"🏆 Побеждает {game.name(w)}!")


# =========================================================
# КОМАНДЫ
# =========================================================

def command_is(*names: str):
    def check(message: Message) -> bool:
        head = ((message.text or "").strip().split(maxsplit=1) or [""])[0].lower()
        head = head.split("@", 1)[0]
        return head in names
    return check


async def create(message: Message, kind: str, opener=None) -> None:
    _cleanup()
    user = opener or message.from_user
    if not games_on(message.chat.id):
        await message.answer("🎲 Игры в этой группе выключены (/settings).")
        return
    game = Game(gid=secrets.token_hex(4), kind=kind, chat_id=message.chat.id,
                players=[(user.id, display_name_of(user))])
    reply = message.reply_to_message if opener is None else None
    if reply and reply.from_user and not reply.from_user.is_bot and reply.from_user.id != user.id:
        game.invited = reply.from_user.id
        game.note = display_name_of(reply.from_user)
    _games[game.gid] = game
    if message.chat.type == "private":
        game.players.append((BOT_ID, BOT_NAME))
        start(game)
        if kind == "checkers":
            game.turn_white = game.turn
    text, markup = view(game)
    sent = await message.answer(text, reply_markup=markup)
    if game.status == "playing" and game.vs_bot and game.turn == 1:
        async with game.lock:
            await bot_turns(sent, game)


@router.message(Command("games", "ttt", "checkers", "seabattle", "rps", "heads", "orel"))
@router.message(command_is("/игры", "/крестики", "/шашки", "/морской", "/кнб", "/орел", "/орёл", "/монетка"))
async def table_command(message: Message):
    head = (message.text or "").strip().split(maxsplit=1)[0].lower().split("@", 1)[0].lstrip("/")
    kind = {
        "ttt": "ttt", "крестики": "ttt", "checkers": "checkers", "шашки": "checkers",
        "seabattle": "sea", "морской": "sea", "rps": "rps", "кнб": "rps",
        "heads": "coin", "orel": "coin", "орел": "coin", "орёл": "coin", "монетка": "coin",
    }.get(head)
    if kind == "coin":
        await coin_start(message)
    elif kind:
        await create(message, kind)
    else:
        await menu(message)


async def menu(message: Message) -> None:
    rows = [
        [InlineKeyboardButton(text="❌⭕ Крестики-нолики", callback_data="tm:ttt"),
         InlineKeyboardButton(text="⚫ Шашки", callback_data="tm:checkers")],
        [InlineKeyboardButton(text="🚢 Морской бой", callback_data="tm:sea"),
         InlineKeyboardButton(text="✊ Камень-ножницы", callback_data="tm:rps")],
        [InlineKeyboardButton(text="🪙 Орёл или решка", callback_data="tm:coin")],
    ]
    await message.answer(
        "🎲 <b>Игры Маруськи</b>\n\nВыбери игру — Маруська откроет стол прямо здесь.\n"
        "Чтобы вызвать конкретного человека, ответь на его сообщение командой: "
        "/крестики, /шашки, /морской, /кнб, /орел.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("tm:"))
async def menu_pick(callback: CallbackQuery):
    kind = (callback.data or "").split(":", 1)[1]
    await callback.answer()
    if callback.message is None:
        return
    if kind == "coin":
        await coin_start(callback.message, opener=callback.from_user)
    elif kind in TITLES:
        await create(callback.message, kind, opener=callback.from_user)


# =========================================================
# ОРЁЛ ИЛИ РЕШКА
# =========================================================

async def coin_start(message: Message, opener=None) -> None:
    if not games_on(message.chat.id):
        await message.answer("🎲 Игры в этой группе выключены (/settings).")
        return
    user = opener or message.from_user
    reply = message.reply_to_message if opener is None else None
    if reply and reply.from_user and not reply.from_user.is_bot and reply.from_user.id != user.id:
        a, b = escape(display_name_of(user)), escape(display_name_of(reply.from_user))
        sent = await message.answer(f"🪙 Дуэль! <b>{a}</b> — 🦅 орёл, <b>{b}</b> — решка.\nПодбрасываем…")
        await asyncio.sleep(1.5)
        heads = random.random() < 0.5
        winner = a if heads else b
        await sent.edit_text(
            f"🪙 Дуэль! <b>{a}</b> — 🦅 орёл, <b>{b}</b> — решка.\n\n"
            f"Выпал{'' if heads else 'а'} <b>{'орёл 🦅' if heads else 'решка 🪙'}</b>! Победа за <b>{winner}</b> 🏆"
        )
        return
    rows = [[InlineKeyboardButton(text="🦅 Орёл", callback_data="tc:heads"),
             InlineKeyboardButton(text="🪙 Решка", callback_data="tc:tails")]]
    await message.answer("🪙 <b>Орёл или решка?</b>\nУгадай, что выпадет!", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


_flipping: set[tuple[int, int]] = set()


@router.callback_query(F.data.in_({"tc:heads", "tc:tails"}))
async def coin_guess(callback: CallbackQuery):
    guess = (callback.data or "").split(":", 1)[1]
    await callback.answer()
    message = callback.message
    if message is None:
        return
    key = (message.chat.id, message.message_id)
    if key in _flipping:
        return  # кто-то уже нажал раньше
    _flipping.add(key)
    name = escape(display_name_of(callback.from_user))
    said = "орёл 🦅" if guess == "heads" else "решку 🪙"
    try:
        await message.edit_text(f"🪙 <b>{name}</b> ставит на {said}…\nМонетка в воздухе…")
    except TelegramBadRequest:
        return
    await asyncio.sleep(1.5)
    heads = random.random() < 0.5
    won = heads == (guess == "heads")
    result = "орёл 🦅" if heads else "решка 🪙"
    tail = random.choice(("Везунчик! 🍀", "Интуиция не подвела 😎", "Чистая победа 🏆")) if won else random.choice(
        ("Не повезло 🙈", "Монетка сегодня не на твоей стороне", "В следующий раз точно!")
    )
    rows = [[InlineKeyboardButton(text="🔄 Ещё раз", callback_data="tc:new")]]
    await message.edit_text(
        f"🪙 <b>{name}</b> ставил(а) на {said}\nВыпал{'' if heads else 'а'} <b>{result}</b>!\n\n{tail}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data == "tc:new")
async def coin_again(callback: CallbackQuery):
    await callback.answer()
    if callback.message:
        await coin_start(callback.message, opener=callback.from_user)


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
            await message.edit_text(f"{TITLES[game.kind]}\n\nСтол закрыт.")
            return

        if act in ("join", "bot"):
            if game.status != "lobby":
                await callback.answer("Игра уже началась")
                return
            if act == "bot":
                if me != 0:
                    await callback.answer("Позвать Маруську может только тот, кто открыл стол")
                    return
                game.players.append((BOT_ID, BOT_NAME))
            else:
                if me == 0:
                    await callback.answer("Ждём соперника — или нажми «С Маруськой»")
                    return
                if game.invited and user.id != game.invited:
                    await callback.answer("Этот вызов не тебе 😉")
                    return
                game.players.append((user.id, display_name_of(user)))
            start(game)
            if game.kind == "checkers":
                game.turn_white = game.turn
            await callback.answer("Поехали!")
            await redraw(message, game)
            await bot_turns(message, game)
            return

        if act == "again":
            if game.status != "over" or me is None:
                await callback.answer("Реванш могут начать только игроки")
                return
            first = 1 - game.turn_white
            start(game)
            if game.kind == "checkers":
                game.turn_white = first
                game.turn = first
            await callback.answer("Реванш!")
            await redraw(message, game)
            await bot_turns(message, game)
            return

        if act == "fleet":
            if me is None or game.kind != "sea" or game.status == "lobby":
                await callback.answer("Это для игроков")
                return
            sea: Sea = game.state[me]
            marks = {"·": "·", "•": "•", "💥": "×", "❌": "×", "🚢": "■"}
            lines = ["".join(marks[sea_cell(sea, r * SIZE + c, True)] for c in range(SIZE)) for r in range(SIZE)]
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
            finish(game, other, f"🏳 {game.name(me)} сдаётся. Победа за {game.name(other)}!")
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
                resolve_rps(game)
            await redraw(message, game)
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
            ttt_after(game)

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
                checkers_after(game)

        elif game.kind == "sea" and act == "s":
            if sea_fire(game, pos) == "again":
                await callback.answer("Сюда уже стреляли")
                return

        else:
            await callback.answer()
            return

        await callback.answer()
        await redraw(message, game)
        await bot_turns(message, game)
