"""
Проверка аналитики: сравнение периодов и соответствие счётчиков
таблице и миграциям.

Запуск:  python test_analytics.py
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).parent

repo = (ROOT / "database" / "repository.py").read_text(encoding="utf-8")
models = (ROOT / "database" / "models.py").read_text(encoding="utf-8")
migrations = (ROOT / "database" / "database.py").read_text(encoding="utf-8")


def main() -> int:
    failures, checks = [], 0

    def expect(label, got, want):
        nonlocal checks
        checks += 1
        if got != want:
            failures.append(f"  {label}: получили {got!r}, ждали {want!r}")

    # --- сравнение с прошлым периодом ---
    ns = {}
    exec(repo[repo.index("def compare("):repo.index("async def analytics_summary(")], ns)
    compare = ns["compare"]

    expect("рост", compare(120, 100), 20)
    expect("падение", compare(80, 100), -20)
    expect("без изменений", compare(50, 50), 0)
    expect("не с чем сравнить", compare(10, 0), None)
    expect("округление", compare(1, 3), -67)

    # --- каждый счётчик: колонка в модели и миграция для старых баз ---
    fields = re.search(r"DAILY_FIELDS = \((.*?)\)", repo, re.S).group(1)
    fields = re.findall(r'"(\w+)"', fields)

    daily_model = models[models.index("class DailyStat(Base):"):]
    daily_model = daily_model[:daily_model.index("\nclass ", 10)]

    original = {"messages", "actions", "games", "active_users"}   # были при создании таблицы

    for field in fields:
        checks += 1
        if not re.search(rf"\n    {field}: Mapped", daily_model):
            failures.append(f"  [таблица] счётчик {field!r} есть в DAILY_FIELDS, но нет колонки в DailyStat")

        if field not in original:
            checks += 1
            if not re.search(rf"daily_stats\s+\"?\s*\"?ADD COLUMN IF NOT EXISTS {field}\b", migrations.replace("\n", " ")):
                failures.append(f"  [миграция] для колонки {field!r} нет ALTER TABLE — на старой базе аналитика упадёт")

    if failures:
        print(f"❌ {len(failures)} проблем:\n")
        print("\n".join(failures))
        return 1

    print(f"✅ Все {checks} проверок аналитики прошли. Счётчиков: {len(fields)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
