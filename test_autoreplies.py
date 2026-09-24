"""
Проверка автоответов и исключений памяти Мары.
Запуск:  python test_autoreplies.py
"""

import pathlib
import random
import re
import time
from dataclasses import dataclass
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).parent

# Автоответы — чистая часть без aiogram
src = (ROOT / "features" / "autoreplies.py").read_text(encoding="utf-8")
ns = {"re": re, "random": random, "time": time, "dataclass": dataclass}
exec(src[src.index("MATCHES = ("):src.index("# ---------------------------------------------------------\n# Обработчик")], ns)

# Исключения памяти — из features/chat.py
chat_src = (ROOT / "features" / "chat.py").read_text(encoding="utf-8")
cns = {"re": re}
start = chat_src.index("def parse_exceptions(")
exec(chat_src[start:chat_src.index("def remembers(")], cns)
parse_exceptions = cns["parse_exceptions"]


def main() -> int:
    failures, checks = [], 0

    def expect(label, got, want):
        nonlocal checks
        checks += 1
        if got != want:
            failures.append(f"  {label}: получили {got!r}, ждали {want!r}")

    Rule, matches, validate, render = ns["Rule"], ns["matches"], ns["validate"], ns["render"]

    contains = Rule(id=1, trigger="кот", response="мяу")
    expect("содержит — слово", matches(contains, "у меня кот"), True)
    expect("содержит — не кусок слова", matches(contains, "который час"), False)
    expect("регистр и знаки", matches(contains, "КОТ!!!"), True)

    phrase = Rule(id=2, trigger="доброе утро", response="☀️")
    expect("фраза", matches(phrase, "Всем доброе утро!"), True)
    expect("ё = е", matches(Rule(id=9, trigger="ещё", response="x"), "дай еще"), True)

    exact = Rule(id=3, trigger="привет", response="хай", match="exact")
    expect("точно — да", matches(exact, "Привет!"), True)
    expect("точно — нет", matches(exact, "привет всем"), False)

    start = Rule(id=4, trigger="мара скажи", response="?", match="start")
    expect("начинается — да", matches(start, "Мара, скажи что-нибудь"), True)
    expect("начинается — нет", matches(start, "эй мара скажи"), False)

    expect("проверка ок", validate("кот", "мяу", "contains", 100, 30), None)
    expect("короткий триггер", bool(validate("к", "мяу", "contains", 100, 30)), True)
    expect("пустой ответ", bool(validate("кот", "  ", "contains", 100, 30)), True)
    expect("вероятность 0", bool(validate("кот", "мяу", "contains", 0, 30)), True)
    expect("вероятность 150", bool(validate("кот", "мяу", "contains", 150, 30)), True)
    expect("чужое совпадение", bool(validate("кот", "мяу", "regex", 100, 30)), True)
    expect("пауза не число", bool(validate("кот", "мяу", "contains", 100, "abc")), True)

    expect("подстановка имени", render("Привет, {name}!", "Стас"), "Привет, Стас!")

    # Вероятность и пауза
    ns["prime"](-100, [
        SimpleNamespace(id=10, trigger="кот", response="мяу", match="contains", probability=50, cooldown=60, enabled=True),
        SimpleNamespace(id=11, trigger="пёс", response="гав", match="contains", probability=100, cooldown=0, enabled=False),
    ])

    find = ns["find"]
    expect("выпала вероятность", (find(-100, "кот", now=0, roll=0.3) or SimpleNamespace(id=None)).id, 10)
    expect("не выпала вероятность", find(-100, "кот", now=0, roll=0.7), None)

    ns["_last_fired"][(-100, 10)] = 100.0
    expect("на паузе", find(-100, "кот", now=130, roll=0.1), None)
    expect("пауза прошла", (find(-100, "кот", now=161, roll=0.1) or SimpleNamespace(id=None)).id, 10)
    expect("выключенный не срабатывает", find(-100, "пёс", now=0, roll=0.0), None)
    expect("в другой группе нет", find(-200, "кот", now=0, roll=0.0), None)

    # Исключения памяти
    expect("разбор исключений", parse_exceptions("@Kate, 12345;  vasya"), {"kate", "12345", "vasya"})
    expect("пусто", parse_exceptions(""), set())

    if failures:
        print(f"❌ {len(failures)} проблем:\n")
        print("\n".join(failures))
        return 1

    print(f"✅ Все {checks} проверок автоответов и памяти прошли.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
