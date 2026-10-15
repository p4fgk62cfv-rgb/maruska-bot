"""
Игры в чате: правила крестиков-ноликов, шашек, морского боя, КНБ — и что
Маруська доигрывает партии до конца сама с собой.
Запуск:  python test_table_games.py
"""

import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from games.table_core import (  # noqa: E402
    FLEET, Checkers, Sea, around, capture_steps, movable, rps_result, sea_bot_target, ttt_bot_move, ttt_winner,
)

errors = []


def check(ok, what):
    if not ok:
        errors.append(what)


# --- крестики-нолики ---
check(ttt_winner(["X", "X", "X", "", "", "", "", "", ""]) == "X", "строка")
check(ttt_winner(["X", "O", "X", "X", "O", "O", "O", "X", "X"]) == "draw", "ничья")
check(ttt_winner([""] * 9) is None, "игра идёт")
# Идеальная Маруська не проигрывает: 200 партий против случайного игрока
rnd = random.Random(1)
for _ in range(200):
    cells, turn = [""] * 9, "X"
    while ttt_winner(cells) is None:
        if turn == "O":
            cells[ttt_bot_move(cells, "O", skill=1.0, rnd=rnd)] = "O"
        else:
            cells[rnd.choice([i for i in range(9) if not cells[i]])] = "X"
        turn = "O" if turn == "X" else "X"
    check(ttt_winner(cells) != "X", "идеальный бот проиграл")
# Она закрывает угрозу
check(ttt_bot_move(["X", "X", "", "", "O", "", "", "", ""], "O", skill=1.0) == 2, "не закрыла угрозу")

# --- шашки ---
g = Checkers()
check(g.count("w") == 12 and g.count("b") == 12, "расстановка")
check(len([d for ds in movable(g.board, "w").values() for d in ds]) == 7, "у белых 7 первых ходов")
# Взятие обязательно и назад тоже
b = [""] * 64
b[4 * 8 + 3] = "w"
b[5 * 8 + 4] = "b"
check(capture_steps(b, 4 * 8 + 3) == [(6 * 8 + 5, 5 * 8 + 4)], "простая бьёт назад")
# Дамка бьёт издалека и может встать на любую клетку за побитой
b = [""] * 64
b[7 * 8 + 0] = "W"
b[4 * 8 + 3] = "b"
lands = sorted(to for to, _ in capture_steps(b, 7 * 8 + 0))
check(lands == sorted([3 * 8 + 4, 2 * 8 + 5, 1 * 8 + 6, 0 * 8 + 7]), f"дамка: {lands}")
# Цепочка: белая бьёт две подряд за один ход, ход не переходит до конца
g = Checkers()
g.board = [""] * 64
g.board[7 * 8 + 0] = "w"
g.board[6 * 8 + 1] = "b"
g.board[4 * 8 + 3] = "b"
g.board[0 * 8 + 1] = "b"
check(g.move(7 * 8 + 0, 5 * 8 + 2), "первый прыжок")
check(g.turn == "w" and g.chain == 5 * 8 + 2, "цепочка продолжается")
check(not g.move(0 * 8 + 1, 1 * 8 + 0), "чужой ход в цепочке запрещён")
check(g.move(5 * 8 + 2, 3 * 8 + 4), "второй прыжок")
check(g.turn == "b" and g.count("b") == 1, "обе побиты, ход чёрных")
# Превращение в дамку
g = Checkers()
g.board = [""] * 64
g.board[1 * 8 + 2] = "w"
g.board[7 * 8 + 0] = "b"
g.move(1 * 8 + 2, 0 * 8 + 1)
check(g.board[1] == "W", "дамка")
# Маруська сама с собой доигрывает: правила не зависают
rnd = random.Random(7)
for game in range(30):
    g = Checkers()
    for _ in range(600):
        if g.winner:
            break
        step = g.bot_step(rnd)
        check(step is not None and g.move(*step), "бот предложил недопустимый ход")
    check(g.winner is not None, f"партия {game} не закончилась")

# --- морской бой ---
rnd = random.Random(3)
for _ in range(200):
    sea = Sea(rnd)
    cells = [p for s in sea.ships for p in s]
    check(len(cells) == sum(FLEET) == len(set(cells)), "корабли пересекаются")
    for s in sea.ships:
        others = set(cells) - s
        check(not around(s) & others, "корабли касаются")
sea = Sea(random.Random(5))
shots = 0
while not sea.lost() and shots < 64:
    res = sea.shoot(sea_bot_target(sea, random.Random(shots)))
    check(res != "again", "бот стреляет дважды в одну клетку")
    shots += 1
check(sea.lost(), "бот не потопил флот за 64 выстрела")

# --- камень-ножницы-бумага ---
check(rps_result("rock", "scissors") == 1 and rps_result("rock", "paper") == -1 and rps_result("paper", "paper") == 0, "кнб")

if errors:
    print("❌ " + "\n❌ ".join(errors[:20]))
    sys.exit(1)
print("✅ Игры в чате: все проверки правил прошли.")
