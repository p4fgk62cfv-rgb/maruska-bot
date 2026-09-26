"""
Проверка топа болтунов: распознавание запроса, склонения, оформление.
Запуск:  python test_chatters.py
"""

import pathlib
import re
from html import escape

ROOT = pathlib.Path(__file__).parent
src = (ROOT / "features" / "chatters.py").read_text(encoding="utf-8")
ns = {"re": re, "escape": escape}
exec(src[src.index("TEXT_RE = "):src.index("# ---------------------------------------------------------\n# Обработчики")], ns)


def main() -> int:
    failures, checks = [], 0

    def expect(label, got, want):
        nonlocal checks
        checks += 1
        if got != want:
            failures.append(f"  {label}: получили {got!r}, ждали {want!r}")

    wanted = ns["is_top_request"]

    for text in ("/топ болтунов", "топ болтунов", "Топ Болтунов!", "/ топ болтунов", "топ болтуны"):
        expect(f"запрос «{text}»", wanted(text), True)

    for text in ("кто в топ болтунов попал?", "топ", "болтунов", "мой топ болтунов вчера", "", None):
        expect(f"не запрос «{text}»", wanted(text), False)

    plural = ns["plural_messages"]
    for n, word in [(1, "сообщение"), (2, "сообщения"), (5, "сообщений"), (11, "сообщений"),
                    (21, "сообщение"), (22, "сообщения"), (112, "сообщений"), (0, "сообщений")]:
        expect(f"{n} {word}", plural(n), word)

    fmt = ns["format_top"]
    people = [{"name": "Стас", "messages": 50}, {"name": "Катя", "messages": 20}, {"name": "<b>Хакер</b>", "messages": 5},
              {"name": "Вася", "messages": 1}]
    text = fmt(people, 76, 4, "26.09")

    expect("первое место — золото", "🥇 <b>Стас</b> — 50 сообщений" in text, True)
    expect("четвёртое — цифрой", "4. <b>Вася</b> — 1 сообщение" in text, True)
    expect("доля от общего", "· 66%" in text, True)
    expect("имя экранируется", "&lt;b&gt;Хакер&lt;/b&gt;" in text, True)
    expect("итог", "Всего сегодня: 76 сообщений от 4 чел." in text, True)
    expect("подколка лидера", "болтает за двоих" in text, True)
    expect("пусто", fmt([], 0, 0, "26.09").startswith("🗣 Сегодня ещё никто"), True)

    if failures:
        print(f"❌ {len(failures)} проблем:\n")
        print("\n".join(failures))
        return 1

    print(f"✅ Все {checks} проверок топа болтунов прошли.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
