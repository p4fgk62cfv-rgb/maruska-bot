"""
Проверка фильтров и сортировок участников.
Запуск:  python test_members.py
"""

import pathlib
import re
from datetime import datetime, timedelta

ROOT = pathlib.Path(__file__).parent
source = (ROOT / "database" / "repository.py").read_text(encoding="utf-8")

ns = {"datetime": datetime}
exec(source[source.index("MEMBER_SORTS = {"):source.index("async def members_page(")], ns)

select = ns["select_members"]
NOW = datetime(2026, 9, 24, 12, 0)


def person(uid, name, **kw):
    item = {
        "telegram_id": uid, "name": name, "username": None,
        "last_seen": NOW - timedelta(hours=2), "joined": NOW - timedelta(days=100),
        "messages": 0, "coins": 0, "xp": 0, "karma": 0, "level": 1,
        "warnings": 0, "vip": False, "admin": False, "blocked": False, "left": False,
    }
    item.update(kw)
    return item


PEOPLE = [
    person(1, "Стас", username="stanislav", coins=15230, xp=8450, messages=4821, level=25, admin=True, vip=True),
    person(2, "Катя", username="katerina", coins=12480, xp=5000, karma=87, joined=NOW - timedelta(days=2)),
    person(3, "Вася", coins=100, warnings=3, last_seen=NOW - timedelta(days=40)),
    person(4, "Олеся", last_seen=NOW - timedelta(days=120), messages=10),
    person(5, "Дмитрий", left=True, coins=999999),
    person(6, "Алекс", blocked=True, last_seen=NOW - timedelta(minutes=5)),
]


def names(flt="all", sort="activity", query=""):
    return [p["name"] for p in select([dict(p) for p in PEOPLE], flt, sort, query, NOW)]


def main() -> int:
    failures, checks = [], 0

    def expect(label, got, want):
        nonlocal checks
        checks += 1
        if got != want:
            failures.append(f"  {label}: получили {got!r}, ждали {want!r}")

    expect("все — без вышедших", sorted(names()), sorted(["Стас", "Катя", "Вася", "Олеся", "Алекс"]))
    expect("активные за сутки", sorted(names("active")), sorted(["Стас", "Катя", "Алекс"]))
    expect("новые за неделю", names("new"), ["Катя"])
    expect("VIP", names("vip"), ["Стас"])
    expect("нарушители", names("violators"), ["Вася"])
    expect("админы", names("admins"), ["Стас"])
    expect("неактивные 30 дней", sorted(names("inactive30")), ["Вася", "Олеся"])
    expect("неактивные 90 дней", names("inactive90"), ["Олеся"])
    expect("в игноре", names("ignored"), ["Алекс"])
    expect("вышли", names("left"), ["Дмитрий"])
    expect("вышедший не в общем списке даже богатый", "Дмитрий" in names(sort="coins"), False)

    expect("сортировка по алмазам", names(sort="coins")[:2], ["Стас", "Катя"])
    expect("по карме", names(sort="karma")[0], "Катя")
    expect("по нарушениям", names(sort="warnings")[0], "Вася")
    expect("по дате вступления — новые сверху", names(sort="joined")[0], "Катя")
    expect("по активности — свежие сверху", names(sort="activity")[0], "Алекс")
    expect("неизвестная сортировка не падает", len(names(sort="ерунда")), 5)

    expect("поиск по имени", names(query="кат"), ["Катя"])
    expect("поиск по @username", names(query="@stanis"), ["Стас"])
    expect("поиск по ID", names(query="3"), ["Вася"])
    expect("поиск + фильтр", names("violators", query="кат"), [])

    if failures:
        print(f"❌ {len(failures)} проблем:\n")
        print("\n".join(failures))
        return 1

    print(f"✅ Все {checks} проверок участников прошли.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
