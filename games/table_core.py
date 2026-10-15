"""
Правила игр в чате: крестики-нолики, шашки, морской бой, камень-ножницы-бумага.

Только логика, без Telegram: всё здесь проверяется тестами (test_table_games.py).
"""

import random

# =========================================================
# КРЕСТИКИ-НОЛИКИ
# =========================================================

LINES = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
)


def ttt_winner(cells: list[str]) -> str | None:
    """'X' или 'O' — победитель, 'draw' — ничья, None — игра идёт."""
    for a, b, c in LINES:
        if cells[a] and cells[a] == cells[b] == cells[c]:
            return cells[a]
    return "draw" if all(cells) else None


def ttt_line(cells: list[str]) -> tuple[int, int, int] | None:
    for line in LINES:
        a, b, c = line
        if cells[a] and cells[a] == cells[b] == cells[c]:
            return line
    return None


def _minimax(cells: list[str], me: str, turn: str) -> int:
    win = ttt_winner(cells)
    if win == me:
        return 1
    if win == "draw":
        return 0
    if win:
        return -1
    other = "O" if turn == "X" else "X"
    scores = []
    for i in range(9):
        if not cells[i]:
            cells[i] = turn
            scores.append(_minimax(cells, me, other))
            cells[i] = ""
    return max(scores) if turn == me else min(scores)


def ttt_bot_move(cells: list[str], me: str, skill: float = 0.8, rnd=random) -> int:
    """Ход Маруськи: обычно лучший, иногда случайный — чтобы её можно было обыграть."""
    free = [i for i in range(9) if not cells[i]]
    if rnd.random() > skill:
        return rnd.choice(free)
    other = "O" if me == "X" else "X"
    best, moves = -2, []
    for i in free:
        cells[i] = me
        score = _minimax(cells, me, other)
        cells[i] = ""
        if score > best:
            best, moves = score, [i]
        elif score == best:
            moves.append(i)
    return rnd.choice(moves)


# =========================================================
# ШАШКИ (русские: бьют назад, дамка ходит далеко, бить обязательно)
# =========================================================
#
# Доска — 64 клетки, индекс r*8+c, r=0 — верх. Белые («w») внизу и ходят вверх.
# Клетка: "" | "w" | "W" (белая дамка) | "b" | "B".

DIRS = ((-1, -1), (-1, 1), (1, -1), (1, 1))


def checkers_start() -> list[str]:
    board = [""] * 64
    for r in range(8):
        for c in range(8):
            if (r + c) % 2 == 1:
                if r < 3:
                    board[r * 8 + c] = "b"
                elif r > 4:
                    board[r * 8 + c] = "w"
    return board


def side_of(piece: str) -> str:
    return piece.lower() if piece else ""


def _inside(r: int, c: int) -> bool:
    return 0 <= r < 8 and 0 <= c < 8


def capture_steps(board: list[str], pos: int, captured: frozenset = frozenset()) -> list[tuple[int, int]]:
    """Прыжки фигуры с клетки pos: (куда, кого бьёт). Уже побитых за этот ход второй раз не бьют."""
    piece = board[pos]
    me = side_of(piece)
    king = piece.isupper()
    r0, c0 = divmod(pos, 8)
    out = []
    for dr, dc in DIRS:
        r, c = r0 + dr, c0 + dc
        if king:
            while _inside(r, c) and not board[r * 8 + c]:
                r, c = r + dr, c + dc
        if not _inside(r, c):
            continue
        victim = r * 8 + c
        if not board[victim] or side_of(board[victim]) == me or victim in captured:
            continue
        r, c = r + dr, c + dc
        while _inside(r, c) and not board[r * 8 + c]:
            out.append((r * 8 + c, victim))
            if not king:
                break
            r, c = r + dr, c + dc
    return out


def quiet_steps(board: list[str], pos: int) -> list[int]:
    piece = board[pos]
    king = piece.isupper()
    forward = -1 if side_of(piece) == "w" else 1
    r0, c0 = divmod(pos, 8)
    out = []
    for dr, dc in DIRS:
        if not king and dr != forward:
            continue
        r, c = r0 + dr, c0 + dc
        while _inside(r, c) and not board[r * 8 + c]:
            out.append(r * 8 + c)
            if not king:
                break
            r, c = r + dr, c + dc
    return out


def movable(board: list[str], side: str) -> dict[int, list[int]]:
    """Какие фигуры и куда могут пойти. Если есть взятие — только взятия."""
    caps = {}
    for pos, piece in enumerate(board):
        if side_of(piece) == side:
            steps = capture_steps(board, pos)
            if steps:
                caps[pos] = [to for to, _ in steps]
    if caps:
        return caps
    quiet = {}
    for pos, piece in enumerate(board):
        if side_of(piece) == side:
            steps = quiet_steps(board, pos)
            if steps:
                quiet[pos] = steps
    return quiet


class Checkers:
    def __init__(self):
        self.board = checkers_start()
        self.turn = "w"
        self.chain: int | None = None          # фигура, которая продолжает бить
        self.captured: set[int] = set()        # побиты в этом ходе, снимаются в конце
        self.quiet_moves = 0                   # ходов дамками без взятий подряд
        self.winner: str | None = None         # "w" | "b" | "draw"
        self.last: tuple[int, int] | None = None

    def options(self) -> dict[int, list[int]]:
        if self.winner:
            return {}
        if self.chain is not None:
            return {self.chain: [to for to, _ in capture_steps(self.board, self.chain, frozenset(self.captured))]}
        return movable(self.board, self.turn)

    def move(self, src: int, dst: int) -> bool:
        """Один шаг. True — ход принят. Ход переходит сопернику, когда бить больше нечего."""
        if dst not in self.options().get(src, []):
            return False
        piece = self.board[src]
        jump = dict(capture_steps(self.board, src, frozenset(self.captured)))
        self.board[dst], self.board[src] = piece, ""
        self.last = (src, dst)
        r = dst // 8
        if piece == "w" and r == 0:
            self.board[dst] = "W"
        elif piece == "b" and r == 7:
            self.board[dst] = "B"
        if dst in jump:
            self.captured.add(jump[dst])
            self.quiet_moves = 0
            if capture_steps(self.board, dst, frozenset(self.captured)):
                self.chain = dst
                return True
        elif piece.isupper():
            self.quiet_moves += 1
        else:
            self.quiet_moves = 0
        self._end_turn()
        return True

    def _end_turn(self) -> None:
        for pos in self.captured:
            self.board[pos] = ""
        self.captured.clear()
        self.chain = None
        self.turn = "b" if self.turn == "w" else "w"
        if not movable(self.board, self.turn):
            self.winner = "b" if self.turn == "w" else "w"
        elif self.quiet_moves >= 30:
            self.winner = "draw"

    def count(self, side: str) -> int:
        return sum(1 for p in self.board if side_of(p) == side)

    def bot_step(self, rnd=random) -> tuple[int, int] | None:
        """Ход Маруськи: бьёт, когда может, бережёт свои шашки, тянется в дамки."""
        opts = self.options()
        if not opts:
            return None
        moves = [(s, d) for s, ds in opts.items() for d in ds]

        def risk(s: int, d: int) -> float:
            board = list(self.board)
            board[d], board[s] = board[s], ""
            enemy = "b" if self.turn == "w" else "w"
            danger = any(victim == d for p, piece in enumerate(board) if side_of(piece) == enemy
                         for _, victim in capture_steps(board, p))
            row = d // 8
            advance = (7 - row) if self.turn == "w" else row
            return (5 if danger else 0) - advance * 0.1 + rnd.random() * 0.5

        return min(moves, key=lambda m: risk(*m))


# =========================================================
# МОРСКОЙ БОЙ (8×8: 4, 3, 2, 2, 1, 1)
# =========================================================

FLEET = (4, 3, 2, 2, 1, 1)
SIZE = 8


class Sea:
    def __init__(self, rnd=random):
        self.ships: list[set[int]] = place_fleet(rnd)
        self.shots: set[int] = set()

    def ship_at(self, pos: int) -> set[int] | None:
        for ship in self.ships:
            if pos in ship:
                return ship
        return None

    def shoot(self, pos: int) -> str:
        """'miss' | 'hit' | 'sunk' | 'again' (уже стреляли)."""
        if pos in self.shots:
            return "again"
        self.shots.add(pos)
        ship = self.ship_at(pos)
        if not ship:
            return "miss"
        if ship <= self.shots:
            # Вокруг потопленного — пусто: отмечаем, чтобы туда не стреляли
            self.shots |= around(ship)
            return "sunk"
        return "hit"

    def lost(self) -> bool:
        return all(ship <= self.shots for ship in self.ships)

    def alive(self) -> int:
        return sum(1 for ship in self.ships if not ship <= self.shots)


def around(cells: set[int]) -> set[int]:
    out = set()
    for pos in cells:
        r0, c0 = divmod(pos, SIZE)
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                r, c = r0 + dr, c0 + dc
                if 0 <= r < SIZE and 0 <= c < SIZE:
                    out.add(r * SIZE + c)
    return out - cells


def place_fleet(rnd=random) -> list[set[int]]:
    while True:
        ships, busy = [], set()
        for length in FLEET:
            for _ in range(200):
                horizontal = rnd.random() < 0.5
                r = rnd.randrange(SIZE if horizontal else SIZE - length + 1)
                c = rnd.randrange(SIZE - length + 1 if horizontal else SIZE)
                cells = {(r * SIZE + c + i) if horizontal else ((r + i) * SIZE + c) for i in range(length)}
                if not cells & busy:
                    ships.append(cells)
                    busy |= cells | around(cells)
                    break
            else:
                break
        if len(ships) == len(FLEET):
            return ships


def sea_bot_target(sea: Sea, rnd=random) -> int:
    """Куда стреляет Маруська: добивает раненый корабль, иначе — в шахматном порядке."""
    wounded = [p for p in sea.shots if sea.ship_at(p) and not sea.ship_at(p) <= sea.shots]
    free = [p for p in range(SIZE * SIZE) if p not in sea.shots]
    if wounded:
        line = sorted(wounded)
        cand = set()
        if len(line) > 1:
            horizontal = line[0] // SIZE == line[1] // SIZE
            if horizontal:
                r = line[0] // SIZE
                for p in (line[0] - 1, line[-1] + 1):
                    if 0 <= p < SIZE * SIZE and p // SIZE == r:
                        cand.add(p)
            else:
                cand |= {line[0] - SIZE, line[-1] + SIZE}
        else:
            r, c = divmod(line[0], SIZE)
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                if 0 <= r + dr < SIZE and 0 <= c + dc < SIZE:
                    cand.add((r + dr) * SIZE + c + dc)
        cand = [p for p in cand if 0 <= p < SIZE * SIZE and p not in sea.shots]
        if cand:
            return rnd.choice(cand)
    checker = [p for p in free if (p // SIZE + p % SIZE) % 2 == 0]
    return rnd.choice(checker or free)


# =========================================================
# КАМЕНЬ-НОЖНИЦЫ-БУМАГА
# =========================================================

RPS = {"rock": ("🪨", "Камень"), "scissors": ("✂️", "Ножницы"), "paper": ("📄", "Бумага")}
BEATS = {"rock": "scissors", "scissors": "paper", "paper": "rock"}


def rps_result(a: str, b: str) -> int:
    """1 — победил первый, -1 — второй, 0 — ничья."""
    if a == b:
        return 0
    return 1 if BEATS[a] == b else -1
