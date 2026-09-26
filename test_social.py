"""
Проверка пары дня и браков.
Запуск:  python test_social.py
"""

import pathlib
import random
import re
import time
from datetime import datetime
from html import escape

ROOT = pathlib.Path(__file__).parent
src = (ROOT / "features" / "social.py").read_text(encoding="utf-8")
ns = {"re": re, "random": random, "time": time, "datetime": datetime, "escape": escape}
exec(src[src.index("PROPOSAL_TTL = "):src.index("# ---------------------------------------------------------\n# Пара дня\n")], ns)


def main() -> int:
    failures, checks = [], 0

    def expect(label, got, want):
        nonlocal checks
        checks += 1
        if got != want:
            failures.append(f"  {label}: получили {got!r}, ждали {want!r}")

    pair, marry = ns["is_pair_request"], ns["is_marry_request"]

    for t in ("пара дня", "/пара дня", "Пара дня!", "пара  дня?"):
        expect(f"пара «{t}»", pair(t), True)
    for t in ("кто пара дня вчера была", "пара", "дня", "", None):
        expect(f"не пара «{t}»", pair(t), False)

    for t in ("брак", "/брак", "Выходи за меня!", "будь моей", "будь моим мужем", "пожениться?"):
        expect(f"предложение «{t}»", marry(t), True)
    for t in ("у нас брак на производстве", "будь моей подругой", "", None):
        expect(f"не предложение «{t}»", marry(t), False)

    plural = ns["plural_days"]
    for n, w in [(1, "день"), (2, "дня"), (5, "дней"), (11, "дней"), (21, "день"), (34, "дня"), (111, "дней")]:
        expect(f"{n} {w}", plural(n), w)

    together = ns["days_together"]
    expect("в день свадьбы — 1 день", together(datetime(2026, 9, 26, 9), datetime(2026, 9, 26, 23)), 1)
    expect("на следующий день — 2", together(datetime(2026, 9, 26, 23), datetime(2026, 9, 27, 1)), 2)
    expect("через месяц", together(datetime(2026, 8, 27), datetime(2026, 9, 26)), 31)

    choose = ns["choose_pair"]
    people = [{"telegram_id": i, "name": f"u{i}"} for i in (1, 2, 3)]
    rng = random.Random(1)

    for _ in range(30):
        got = choose(people + [{"telegram_id": 999, "name": "Мара"}], {999}, rng)
        checks += 1
        if got is None or 999 in (got[0]["telegram_id"], got[1]["telegram_id"]) or got[0] is got[1]:
            failures.append("  выбор пары: попал бот или один и тот же человек дважды")
            break

    expect("один человек — пары нет", choose([people[0]], set(), rng), None)
    expect("никого — пары нет", choose([], set(), rng), None)

    expect("упоминание экранирует имя", ns["mention"](5, "<b>x</b>"), '<a href="tg://user?id=5">&lt;b&gt;x&lt;/b&gt;</a>')

    alive = ns["proposal_alive"]
    expect("предложение свежее", alive(100.0, 500.0), True)
    expect("предложение протухло", alive(100.0, 701.0), False)
    expect("предложения не было", alive(None, 1.0), False)

    for phrase in ns["PAIR_PHRASES"]:
        expect(f"фраза собирается: {phrase[:25]}", "{a}" in phrase and "{b}" in phrase and bool(phrase.format(a="A", b="B")), True)

    if failures:
        print(f"❌ {len(failures)} проблем:\n")
        print("\n".join(failures))
        return 1

    print(f"✅ Все {checks} проверок пары дня и браков прошли.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
