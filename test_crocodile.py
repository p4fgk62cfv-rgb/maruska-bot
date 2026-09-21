"""
Проверка Крокодила без запуска бота.

Запуск:  python test_crocodile.py
"""

import re

from games import state
from games.words import ALL_WORDS, WORDS, is_correct_guess, pick_word


START_RE = re.compile(r"\bкрокодил\w*\b", re.IGNORECASE)
WORDS_RE = re.compile(r"[А-Яа-яЁёA-Za-z]+")
MAX_START_WORDS = 4


def is_start(text: str) -> bool:
    if not START_RE.search(text):
        return False
    return len(WORDS_RE.findall(text)) <= MAX_START_WORDS


GUESS_CASES = [
    # (сообщение, загаданное, ожидание)
    ("велосипед", "велосипед", True),
    ("может велосипед?", "велосипед", True),
    ("велосипеда часть", "велосипед", True),
    ("кошку", "кошка", True),
    ("самолёты", "самолёт", True),
    ("мороженого хочу", "мороженое", True),
    ("день рождения", "день рождения", True),
    ("машина", "велосипед", False),
    ("велик", "велосипед", False),
    ("лес", "лес", True),
    ("это точно не оно", "дом", False),
    ("прокрастинация же", "прокрастинация", True),
]

START_CASES = [
    ("крокодил", True),
    ("давай крокодил", True),
    ("Мара, крокодил", True),
    ("играем в крокодила", True),
    ("вчера видел крокодила в зоопарке было круто", False),
    ("а в крокодила поиграем потом когда все соберутся", False),
    ("просто сообщение", False),
]


def main() -> int:
    failures = []

    for text, word, expected in GUESS_CASES:
        got = is_correct_guess(text, word)
        if got != expected:
            failures.append(
                f"  [отгадка] {text!r} на слово {word!r}: "
                f"ждали {expected}, получили {got}"
            )

    for text, expected in START_CASES:
        got = is_start(text)
        if got != expected:
            failures.append(
                f"  [старт] {text!r}: ждали {expected}, получили {got}"
            )

    # Словарь
    if len(ALL_WORDS) != len(set(ALL_WORDS)):
        failures.append("  [словарь] есть дубли слов")

    for level, items in WORDS.items():
        if len(items) < 50:
            failures.append(f"  [словарь] мало слов уровня {level}: {len(items)}")

    for _ in range(200):
        word, level = pick_word()
        if level not in WORDS or word not in WORDS[level]:
            failures.append(f"  [выбор] сломанная пара {word!r}/{level!r}")
            break

    # Состояние раунда
    state.drop(-1)
    item = state.Round(
        round_id=1,
        chat_id=-1,
        host_id=10,
        host_name="Стас",
        word="дом",
        level="easy",
        status="playing",
    )
    state.start(item)

    if state.get(-1) is None:
        failures.append("  [состояние] раунд не сохранился")

    if state.drop(-1) is None or state.get(-1) is not None:
        failures.append("  [состояние] раунд не удалился")

    total = len(GUESS_CASES) + len(START_CASES) + 4

    if failures:
        print(f"❌ {len(failures)} из {total} проверок не прошли:\n")
        print("\n".join(failures))
        return 1

    print(f"✅ Все {total} проверок прошли. Слов в словаре: {len(ALL_WORDS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
